use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    fs,
    io::{Read, Write},
    net::TcpStream,
    path::PathBuf,
    time::Duration,
};
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder, PredefinedMenuItem, SubmenuBuilder},
    AppHandle, Emitter, Manager,
};

mod tools;

const DEFAULT_API_URL: &str = "http://127.0.0.1:8000";

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct AgentReply {
    answer: String,
    sources: Vec<Value>,
    raw: Value,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeHealth {
    status: String,
    api_url: String,
    detail: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PluginManifest {
    name: String,
    display_name: String,
    description: String,
    enabled: bool,
    entry: Option<String>,
    permissions: Vec<String>,
    triggers: Vec<String>,
    version: String,
    source: String,
}

#[derive(Debug, Deserialize)]
struct AskResponse {
    #[serde(default)]
    answer: Option<String>,
    #[serde(default)]
    result: Option<String>,
    #[serde(default)]
    response: Option<String>,
    #[serde(default)]
    output: Option<String>,
    #[serde(default)]
    sources: Vec<Value>,
}

#[tauri::command]
fn agent_chat(message: String) -> Result<AgentReply, String> {
    let api_url = api_url();
    let body = serde_json::json!({ "task": message, "max_rounds": 2 }).to_string();
    let raw = http_json(&api_url, "POST", "/ask", Some(body))
        .map_err(|error| format!("ANUBIS backend unavailable: {error}"))?;
    Ok(normalize_agent_reply(raw))
}

#[tauri::command]
fn runtime_health() -> RuntimeHealth {
    let api_url = api_url();
    match http_json(&api_url, "GET", "/health/live", None) {
        Ok(_) => RuntimeHealth {
            status: "online".into(),
            api_url,
            detail: None,
        },
        Err(error) => RuntimeHealth {
            status: "offline".into(),
            api_url,
            detail: Some(error.to_string()),
        },
    }
}

#[tauri::command]
fn list_plugins(app: AppHandle) -> Result<Vec<PluginManifest>, String> {
    let root = project_root(&app)?;
    let mut manifests = Vec::new();
    manifests.extend(read_plugin_dir(root.join("plugins"))?);
    manifests.extend(read_plugin_dir(root.join("skills"))?);
    manifests.sort_by(|left, right| left.name.cmp(&right.name));
    Ok(manifests)
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let menu = build_menu(app.handle())?;
            app.set_menu(menu)?;
            Ok(())
        })
        .on_menu_event(|app, event| {
            let _ = app.emit("anubis://menu", event.id().0.as_str());
        })
        .invoke_handler(tauri::generate_handler![
            agent_chat,
            runtime_health,
            list_plugins,
            tools::route_tool
        ])
        .run(tauri::generate_context!())
        .expect("failed to run ANUBIS desktop runtime");
}

fn build_menu(app: &AppHandle) -> tauri::Result<tauri::menu::Menu<tauri::Wry>> {
    let file = SubmenuBuilder::new(app, "File")
        .item(&MenuItemBuilder::new("New Chat").id("file:new-chat").accelerator("CmdOrCtrl+N").build(app)?)
        .item(&MenuItemBuilder::new("Open Vault").id("file:open-vault").accelerator("CmdOrCtrl+O").build(app)?)
        .separator()
        .item(&PredefinedMenuItem::quit(app, Some("Quit"))?)
        .build()?;

    let tools = SubmenuBuilder::new(app, "Tools")
        .item(&MenuItemBuilder::new("Command Palette").id("tools:command-palette").accelerator("CmdOrCtrl+K").build(app)?)
        .item(&MenuItemBuilder::new("Sync Vault").id("tools:sync-vault").accelerator("CmdOrCtrl+R").build(app)?)
        .item(&MenuItemBuilder::new("Reload Plugins").id("tools:reload-plugins").build(app)?)
        .build()?;

    let project = SubmenuBuilder::new(app, "Project")
        .item(&MenuItemBuilder::new("Project Memory").id("project:memory").build(app)?)
        .item(&MenuItemBuilder::new("Plugin Manifests").id("project:plugins").build(app)?)
        .build()?;

    let view = SubmenuBuilder::new(app, "View")
        .item(&MenuItemBuilder::new("Focus Mode").id("view:focus-mode").accelerator("CmdOrCtrl+1").build(app)?)
        .item(&MenuItemBuilder::new("Toggle Developer Tools").id("view:devtools").accelerator("F12").build(app)?)
        .build()?;

    MenuBuilder::new(app)
        .items(&[&file, &tools, &project, &view])
        .build()
}

fn normalize_agent_reply(raw: Value) -> AgentReply {
    let parsed = serde_json::from_value::<AskResponse>(raw.clone()).ok();
    let answer = parsed
        .as_ref()
        .and_then(|data| {
            data.answer
                .clone()
                .or_else(|| data.result.clone())
                .or_else(|| data.response.clone())
                .or_else(|| data.output.clone())
        })
        .filter(|text| !text.trim().is_empty())
        .unwrap_or_else(|| raw.to_string());

    let sources = parsed.map(|data| data.sources).unwrap_or_default();
    AgentReply { answer, sources, raw }
}

fn api_url() -> String {
    std::env::var("ANUBIS_API_URL").unwrap_or_else(|_| DEFAULT_API_URL.into())
}

fn http_json(api_url: &str, method: &str, path: &str, body: Option<String>) -> Result<Value, String> {
    let address = api_url
        .trim()
        .strip_prefix("http://")
        .ok_or_else(|| "Only http:// local API URLs are supported".to_string())?;
    let host = address.trim_end_matches('/').to_string();
    let body = body.unwrap_or_default();
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: {host}\r\nContent-Type: application/json\r\nAccept: application/json\r\nConnection: close\r\nContent-Length: {}\r\n\r\n{}",
        body.as_bytes().len(),
        body
    );

    let mut stream = TcpStream::connect(&host).map_err(|error| error.to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(180)))
        .map_err(|error| error.to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_secs(10)))
        .map_err(|error| error.to_string())?;
    stream
        .write_all(request.as_bytes())
        .map_err(|error| error.to_string())?;

    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| error.to_string())?;

    let (head, body) = response
        .split_once("\r\n\r\n")
        .ok_or_else(|| "Malformed HTTP response".to_string())?;
    let status = head
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .unwrap_or("000");

    if !status.starts_with('2') {
        return Err(format!("HTTP {status}"));
    }

    serde_json::from_str(body).map_err(|error| error.to_string())
}

fn project_root(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(root) = std::env::var("ANUBIS_PROJECT_ROOT") {
        return Ok(PathBuf::from(root));
    }

    app.path()
        .resolve("..", tauri::path::BaseDirectory::Resource)
        .or_else(|_| std::env::current_dir())
        .map_err(|error| error.to_string())
}

fn read_plugin_dir(root: PathBuf) -> Result<Vec<PluginManifest>, String> {
    if !root.exists() {
        return Ok(Vec::new());
    }

    let mut manifests = Vec::new();
    for entry in fs::read_dir(root).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let path = entry.path();
        let manifest_path = if path.is_dir() {
            let module_manifest = path.join("manifest.json");
            if module_manifest.exists() {
                module_manifest
            } else {
                path.join("plugin.json")
            }
        } else if path.extension().and_then(|value| value.to_str()) == Some("json")
            && path
                .file_name()
                .and_then(|value| value.to_str())
                .map(|name| name.ends_with(".plugin.json"))
                .unwrap_or(false)
        {
            path
        } else {
            continue;
        };

        if manifest_path.exists() {
            if let Some(manifest) = read_plugin_manifest(&manifest_path)? {
                manifests.push(manifest);
            }
        }
    }

    Ok(manifests)
}

fn read_plugin_manifest(path: &PathBuf) -> Result<Option<PluginManifest>, String> {
    let content = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let raw: Value = serde_json::from_str(&content).map_err(|error| format!("{}: {error}", path.display()))?;
    let Some(name) = raw.get("name").and_then(Value::as_str) else {
        return Ok(None);
    };

    let display_name = raw
        .get("display_name")
        .or_else(|| raw.get("displayName"))
        .and_then(Value::as_str)
        .unwrap_or(name)
        .to_string();

    Ok(Some(PluginManifest {
        name: name.to_string(),
        display_name,
        description: raw
            .get("description")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        enabled: raw.get("enabled").and_then(Value::as_bool).unwrap_or(true),
        entry: raw
            .get("entry")
            .and_then(Value::as_str)
            .map(ToString::to_string),
        permissions: raw
            .get("permissions")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(Value::as_str)
                    .map(ToString::to_string)
                    .collect()
            })
            .unwrap_or_default(),
        triggers: raw
            .get("triggers")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(Value::as_str)
                    .map(ToString::to_string)
                    .collect()
            })
            .unwrap_or_default(),
        version: raw
            .get("version")
            .and_then(Value::as_str)
            .unwrap_or("0.0.0")
            .to_string(),
        source: path.display().to_string(),
    }))
}
