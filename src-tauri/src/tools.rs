use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::AppHandle;

const MAX_FILE_BYTES: usize = 256 * 1024;
const MAX_WRITE_BYTES: usize = 512 * 1024;
const MAX_SEARCH_RESULTS: usize = 200;
const DEFAULT_TIMEOUT_MS: u64 = 10_000;
const MAX_TIMEOUT_MS: u64 = 30_000;

const ALLOWED_COMMANDS: &[&str] = &["rg", "grep", "ls", "pwd", "sed", "cat", "head", "tail", "wc"];
const BLOCKED_TOKENS: &[&str] = &[
    "rm",
    "sudo",
    "su",
    "curl",
    "wget",
    "chmod",
    "chown",
    "mkfs",
    "dd",
    "nc",
    "netcat",
    "ssh",
    "scp",
    "eval",
    "source",
    "bash",
    "sh",
    "zsh",
    "fish",
    "powershell",
];
const BLOCKED_SHELL_PATTERNS: &[&str] = &[
    "&&", "||", "|", ";", "`", "$(", ">", "<", "\n", "\r", "*", "~",
];

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolRequest {
    tool: String,
    #[serde(default)]
    payload: Value,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolResponse {
    tool: String,
    status: String,
    output: Value,
    duration_ms: u128,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct SearchMatch {
    path: String,
    line: usize,
    text: String,
}

#[tauri::command]
pub fn route_tool(app: AppHandle, tool: String, payload: Value) -> Result<ToolResponse, String> {
    let request = ToolRequest { tool, payload };
    let started = Instant::now();
    let root = super::project_root(&app)?;
    let root = canonical_root(&root)?;

    let result = match request.tool.as_str() {
        "read_file" => read_file(&root, &request.payload),
        "write_file" => write_file(&root, &request.payload),
        "search_files" => search_files(&root, &request.payload),
        "run_shell" => run_shell(&root, &request.payload),
        "git" | "git_status" | "git_diff" | "git_log" => git_operation(&root, &request.tool, &request.payload),
        other => Err(format!("Unknown tool: {other}")),
    };

    let duration_ms = started.elapsed().as_millis();
    audit_tool(&root, &request, result.as_ref().map(|_| ()), duration_ms);

    result.map(|output| ToolResponse {
        tool: request.tool,
        status: "ok".into(),
        output,
        duration_ms,
    })
}

fn read_file(root: &Path, payload: &Value) -> Result<Value, String> {
    let path = sandbox_path(root, required_string(payload, "path")?)?;
    let metadata = fs::metadata(&path).map_err(|error| error.to_string())?;
    if !metadata.is_file() {
        return Err("read_file path must be a file".into());
    }
    if metadata.len() as usize > MAX_FILE_BYTES {
        return Err(format!("read_file exceeds {MAX_FILE_BYTES} byte limit"));
    }

    let content = fs::read_to_string(&path).map_err(|error| error.to_string())?;
    Ok(json!({
        "path": relative_display(root, &path),
        "content": content,
        "bytes": metadata.len(),
    }))
}

fn write_file(root: &Path, payload: &Value) -> Result<Value, String> {
    let content = required_string(payload, "content")?;
    if content.len() > MAX_WRITE_BYTES {
        return Err(format!("write_file exceeds {MAX_WRITE_BYTES} byte limit"));
    }

    let path = sandbox_path_for_write(root, required_string(payload, "path")?)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(&path, content).map_err(|error| error.to_string())?;

    Ok(json!({
        "path": relative_display(root, &path),
        "bytes": content.len(),
    }))
}

fn search_files(root: &Path, payload: &Value) -> Result<Value, String> {
    let query = required_string(payload, "query")?.trim().to_lowercase();
    if query.len() < 2 {
        return Err("search_files query must contain at least 2 characters".into());
    }

    let scope = optional_string(payload, "path")
        .map(|path| sandbox_path(root, path))
        .transpose()?
        .unwrap_or_else(|| root.to_path_buf());

    let mut matches = Vec::new();
    collect_search_matches(root, &scope, &query, &mut matches)?;

    Ok(json!({
        "query": query,
        "matches": matches,
    }))
}

fn run_shell(root: &Path, payload: &Value) -> Result<Value, String> {
    let argv = command_argv(payload)?;
    validate_command(&argv)?;
    run_process(root, &argv, timeout_ms(payload))
}

fn git_operation(root: &Path, tool: &str, payload: &Value) -> Result<Value, String> {
    let operation = match tool {
        "git_status" => "status",
        "git_diff" => "diff",
        "git_log" => "log",
        _ => optional_string(payload, "operation").unwrap_or("status"),
    };

    let mut argv = vec!["git".to_string()];
    match operation {
        "status" => argv.extend(["status".into(), "--short".into()]),
        "diff" => argv.extend(["diff".into(), "--".into()]),
        "log" => argv.extend(["log".into(), "--oneline".into(), "-n".into(), "20".into()]),
        "branch" => argv.extend(["branch".into(), "--show-current".into()]),
        "show" => {
            let rev = optional_string(payload, "rev").unwrap_or("HEAD");
            validate_git_rev(rev)?;
            argv.extend(["show".into(), "--stat".into(), "--oneline".into(), rev.into()]);
        }
        other => return Err(format!("Unsupported git operation: {other}")),
    }

    run_process(root, &argv, timeout_ms(payload))
}

fn run_process(root: &Path, argv: &[String], timeout_ms: u64) -> Result<Value, String> {
    let mut child = Command::new(&argv[0])
        .args(&argv[1..])
        .current_dir(root)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| error.to_string())?;

    let deadline = Instant::now() + Duration::from_millis(timeout_ms);
    loop {
        if child.try_wait().map_err(|error| error.to_string())?.is_some() {
            let output = child.wait_with_output().map_err(|error| error.to_string())?;
            return Ok(json!({
                "command": argv,
                "exitCode": output.status.code(),
                "stdout": String::from_utf8_lossy(&output.stdout),
                "stderr": String::from_utf8_lossy(&output.stderr),
            }));
        }

        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("Command timed out after {timeout_ms}ms"));
        }

        thread::sleep(Duration::from_millis(25));
    }
}

fn collect_search_matches(
    root: &Path,
    path: &Path,
    query: &str,
    matches: &mut Vec<SearchMatch>,
) -> Result<(), String> {
    if matches.len() >= MAX_SEARCH_RESULTS {
        return Ok(());
    }

    if path.is_file() {
        search_file(root, path, query, matches)?;
        return Ok(());
    }

    for entry in fs::read_dir(path).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let child = entry.path();
        if should_skip_path(&child) {
            continue;
        }
        let Ok(canonical_child) = child.canonicalize() else {
            continue;
        };
        if ensure_inside(root, &canonical_child).is_err() {
            continue;
        }
        collect_search_matches(root, &child, query, matches)?;
        if matches.len() >= MAX_SEARCH_RESULTS {
            break;
        }
    }

    Ok(())
}

fn search_file(root: &Path, path: &Path, query: &str, matches: &mut Vec<SearchMatch>) -> Result<(), String> {
    if fs::metadata(path).map_err(|error| error.to_string())?.len() as usize > MAX_FILE_BYTES {
        return Ok(());
    }

    let Ok(content) = fs::read_to_string(path) else {
        return Ok(());
    };

    for (index, line) in content.lines().enumerate() {
        if line.to_lowercase().contains(query) {
            matches.push(SearchMatch {
                path: relative_display(root, path),
                line: index + 1,
                text: line.trim().chars().take(500).collect(),
            });
            if matches.len() >= MAX_SEARCH_RESULTS {
                break;
            }
        }
    }

    Ok(())
}

fn validate_command(argv: &[String]) -> Result<(), String> {
    if argv.is_empty() {
        return Err("run_shell command cannot be empty".into());
    }

    let program = argv[0].as_str();
    if !ALLOWED_COMMANDS.contains(&program) {
        return Err(format!("Command is not allowed: {program}"));
    }

    for arg in argv {
        let lower = arg.to_lowercase();
        if BLOCKED_TOKENS.iter().any(|token| lower == *token || lower.starts_with(&format!("{token} "))) {
            return Err(format!("Blocked command token: {arg}"));
        }
        if BLOCKED_SHELL_PATTERNS.iter().any(|pattern| arg.contains(pattern)) {
            return Err(format!("Blocked shell pattern in argument: {arg}"));
        }
        validate_shell_argument(arg)?;
    }

    if program == "sed" && argv.iter().any(|arg| arg == "-i" || arg.starts_with("-i")) {
        return Err("run_shell cannot mutate files with sed -i; use write_file instead".into());
    }

    Ok(())
}

fn validate_shell_argument(arg: &str) -> Result<(), String> {
    let value = arg.trim();
    if value.is_empty() {
        return Ok(());
    }

    if Path::new(value).is_absolute()
        || value == ".."
        || value.starts_with("../")
        || value.contains("/../")
        || value.ends_with("/..")
    {
        return Err(format!("Path escapes are not allowed in shell arguments: {arg}"));
    }

    Ok(())
}

fn command_argv(payload: &Value) -> Result<Vec<String>, String> {
    if let Some(items) = payload.get("argv").and_then(Value::as_array) {
        return items
            .iter()
            .map(|item| {
                item.as_str()
                    .map(ToString::to_string)
                    .ok_or_else(|| "argv must contain only strings".to_string())
            })
            .collect();
    }

    let command = required_string(payload, "command")?;
    if BLOCKED_SHELL_PATTERNS.iter().any(|pattern| command.contains(pattern)) {
        return Err("run_shell command contains blocked shell syntax".into());
    }

    Ok(command.split_whitespace().map(ToString::to_string).collect())
}

fn sandbox_path(root: &Path, value: &str) -> Result<PathBuf, String> {
    validate_relative_path(value)?;
    let path = root.join(value);
    let canonical = path.canonicalize().map_err(|error| error.to_string())?;
    ensure_inside(root, &canonical)?;
    Ok(canonical)
}

fn sandbox_path_for_write(root: &Path, value: &str) -> Result<PathBuf, String> {
    validate_relative_path(value)?;
    let path = root.join(value);
    if path.exists() {
        let canonical = path.canonicalize().map_err(|error| error.to_string())?;
        ensure_inside(root, &canonical)?;
        return Ok(canonical);
    }

    let parent = path.parent().ok_or_else(|| "Invalid path".to_string())?;
    let canonical_parent = parent.canonicalize().map_err(|error| error.to_string())?;
    ensure_inside(root, &canonical_parent)?;
    Ok(path)
}

fn validate_relative_path(value: &str) -> Result<(), String> {
    let path = Path::new(value);
    if value.trim().is_empty() {
        return Err("Path cannot be empty".into());
    }
    if path.is_absolute() {
        return Err("Absolute paths are not allowed".into());
    }
    for component in path.components() {
        match component {
            Component::Normal(_) | Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err("Path escapes the project sandbox".into());
            }
        }
    }
    Ok(())
}

fn ensure_inside(root: &Path, path: &Path) -> Result<(), String> {
    if path.starts_with(root) {
        Ok(())
    } else {
        Err("Path escapes the project sandbox".into())
    }
}

fn canonical_root(root: &Path) -> Result<PathBuf, String> {
    root.canonicalize().map_err(|error| error.to_string())
}

fn should_skip_path(path: &Path) -> bool {
    path.file_name()
        .and_then(|name| name.to_str())
        .map(|name| matches!(name, ".git" | "node_modules" | "target" | "dist" | "__pycache__" | ".venv"))
        .unwrap_or(false)
}

fn required_string<'a>(payload: &'a Value, key: &str) -> Result<&'a str, String> {
    payload
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("Missing string payload field: {key}"))
}

fn optional_string<'a>(payload: &'a Value, key: &str) -> Option<&'a str> {
    payload.get(key).and_then(Value::as_str)
}

fn timeout_ms(payload: &Value) -> u64 {
    payload
        .get("timeoutMs")
        .and_then(Value::as_u64)
        .unwrap_or(DEFAULT_TIMEOUT_MS)
        .min(MAX_TIMEOUT_MS)
}

fn validate_git_rev(value: &str) -> Result<(), String> {
    if value.chars().all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '/' | '.')) {
        Ok(())
    } else {
        Err("Invalid git revision".into())
    }
}

fn relative_display(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn audit_tool(root: &Path, request: &ToolRequest, result: Result<(), &String>, duration_ms: u128) {
    let status = if result.is_ok() { "ok" } else { "error" };
    let error = result.err().map(|error| error.as_str()).unwrap_or("");
    let log = json!({
        "timestamp": unix_timestamp(),
        "tool": request.tool,
        "payload": sanitize_payload(&request.payload),
        "status": status,
        "error": error,
        "durationMs": duration_ms,
    });

    let state_dir = root.join("state");
    let _ = fs::create_dir_all(&state_dir);
    let path = state_dir.join("tauri_tool_audit.jsonl");
    let line = format!("{log}\n");
    let _ = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .and_then(|mut file| {
            use std::io::Write;
            file.write_all(line.as_bytes())
        });
}

fn sanitize_payload(payload: &Value) -> Value {
    let mut clone = payload.clone();
    if let Some(object) = clone.as_object_mut() {
        if let Some(content) = object.get_mut("content") {
            if content.as_str().map(|value| value.len()).unwrap_or(0) > 200 {
                *content = Value::String("[redacted large content]".into());
            }
        }
    }
    clone
}

fn unix_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or_default()
}
