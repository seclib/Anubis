use serde::Serialize;
use std::{
    collections::{HashMap, VecDeque},
    io::{BufRead, BufReader},
    net::{TcpStream, ToSocketAddrs},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};
use tauri::{AppHandle, Emitter, Manager, State};

const LOG_LIMIT: usize = 800;

#[derive(Clone, Serialize)]
struct ServiceStatus {
    name: String,
    label: String,
    status: String,
    detail: String,
    pid: Option<u32>,
}

#[derive(Clone, Serialize)]
struct LauncherStatus {
    services: Vec<ServiceStatus>,
    running: bool,
}

#[derive(Clone, Serialize)]
struct LogLine {
    service: String,
    stream: String,
    line: String,
}

struct ManagedService {
    name: &'static str,
    label: &'static str,
    child: Option<Child>,
}

impl ManagedService {
    fn new(name: &'static str, label: &'static str) -> Self {
        Self {
            name,
            label,
            child: None,
        }
    }
}

struct LauncherState {
    repo_root: PathBuf,
    services: Mutex<HashMap<&'static str, ManagedService>>,
    logs: Mutex<VecDeque<LogLine>>,
}

impl LauncherState {
    fn new(repo_root: PathBuf) -> Self {
        let mut services = HashMap::new();
        services.insert("rag", ManagedService::new("rag", "RAG / Qdrant"));
        services.insert("backend", ManagedService::new("backend", "Backend API"));
        services.insert("agent", ManagedService::new("agent", "Agent Swarm"));
        Self {
            repo_root,
            services: Mutex::new(services),
            logs: Mutex::new(VecDeque::with_capacity(LOG_LIMIT)),
        }
    }
}

type SharedLauncher = Arc<LauncherState>;

fn repo_root() -> PathBuf {
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for candidate in cwd.ancestors() {
        if candidate.join("docker-compose.yml").exists() && candidate.join("backend/main.py").exists() {
            return candidate.to_path_buf();
        }
    }
    cwd.parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .unwrap_or(cwd)
}

fn push_log(state: &LauncherState, app: &AppHandle, service: &str, stream: &str, line: String) {
    let event = LogLine {
        service: service.to_string(),
        stream: stream.to_string(),
        line,
    };
    if let Ok(mut logs) = state.logs.lock() {
        if logs.len() >= LOG_LIMIT {
            logs.pop_front();
        }
        logs.push_back(event.clone());
    }
    let _ = app.emit("anubis-log", event);
}

fn spawn_reader(
    state: SharedLauncher,
    app: AppHandle,
    service: &'static str,
    stream: &'static str,
    reader: impl std::io::Read + Send + 'static,
) {
    thread::spawn(move || {
        let buffered = BufReader::new(reader);
        for line in buffered.lines() {
            match line {
                Ok(text) => push_log(&state, &app, service, stream, text),
                Err(error) => {
                    push_log(&state, &app, service, stream, format!("log stream closed: {error}"));
                    break;
                }
            }
        }
    });
}

fn shell_command(command: &str, cwd: &Path) -> Command {
    let mut cmd = Command::new("bash");
    cmd.arg("-lc")
        .arg(command)
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    cmd
}

fn command_for_service(service: &str) -> Result<String, String> {
    match service {
        "rag" => Ok("docker compose up --no-color qdrant redis".to_string()),
        "backend" => Ok("python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000".to_string()),
        "agent" => Ok(
            "python3 -u -c 'from agent.multi_agent import agent_roster; print(\"agent swarm ready: %s agents\" % len(agent_roster()), flush=True); import time\nwhile True: time.sleep(3600)'"
                .to_string(),
        ),
        _ => Err(format!("unknown service: {service}")),
    }
}

fn start_service(state: &SharedLauncher, app: &AppHandle, service_name: &'static str) -> Result<(), String> {
    let command = command_for_service(service_name)?;
    {
        let mut services = state.services.lock().map_err(|_| "service lock poisoned".to_string())?;
        let service = services
            .get_mut(service_name)
            .ok_or_else(|| format!("unknown service: {service_name}"))?;
        if let Some(child) = service.child.as_mut() {
            if child.try_wait().map_err(|error| error.to_string())?.is_none() {
                push_log(state, app, service_name, "system", "already running".to_string());
                return Ok(());
            }
            service.child = None;
        }
    }

    push_log(
        state,
        app,
        service_name,
        "system",
        format!("starting: {command}"),
    );
    let mut child = shell_command(&command, &state.repo_root)
        .spawn()
        .map_err(|error| format!("failed to start {service_name}: {error}"))?;

    if let Some(stdout) = child.stdout.take() {
        spawn_reader(state.clone(), app.clone(), service_name, "stdout", stdout);
    }
    if let Some(stderr) = child.stderr.take() {
        spawn_reader(state.clone(), app.clone(), service_name, "stderr", stderr);
    }

    let pid = child.id();
    let mut services = state.services.lock().map_err(|_| "service lock poisoned".to_string())?;
    if let Some(service) = services.get_mut(service_name) {
        service.child = Some(child);
    }
    push_log(state, app, service_name, "system", format!("started pid={pid}"));
    Ok(())
}

fn stop_service(state: &SharedLauncher, app: &AppHandle, service_name: &'static str) -> Result<(), String> {
    let mut child = {
        let mut services = state.services.lock().map_err(|_| "service lock poisoned".to_string())?;
        services
            .get_mut(service_name)
            .ok_or_else(|| format!("unknown service: {service_name}"))?
            .child
            .take()
    };

    if let Some(mut process) = child.take() {
        push_log(state, app, service_name, "system", "stopping".to_string());
        if let Err(error) = process.kill() {
            push_log(
                state,
                app,
                service_name,
                "stderr",
                format!("failed to send stop signal: {error}"),
            );
        }
        let _ = process.wait();
        push_log(state, app, service_name, "system", "stopped".to_string());
    }

    if service_name == "rag" {
        let output = shell_command("docker compose stop qdrant redis", &state.repo_root).output();
        match output {
            Ok(result) => {
                if !result.stdout.is_empty() {
                    push_log(
                        state,
                        app,
                        service_name,
                        "stdout",
                        String::from_utf8_lossy(&result.stdout).trim().to_string(),
                    );
                }
                if !result.stderr.is_empty() {
                    push_log(
                        state,
                        app,
                        service_name,
                        "stderr",
                        String::from_utf8_lossy(&result.stderr).trim().to_string(),
                    );
                }
            }
            Err(error) => push_log(
                state,
                app,
                service_name,
                "stderr",
                format!("docker compose stop failed: {error}"),
            ),
        }
    }

    Ok(())
}

fn port_open(port: u16) -> bool {
    let Ok(mut addresses) = ("127.0.0.1", port).to_socket_addrs() else {
        return false;
    };
    let Some(address) = addresses.next() else {
        return false;
    };
    TcpStream::connect_timeout(&address, Duration::from_millis(180)).is_ok()
}

fn memory_detail(repo_root: &Path) -> String {
    let hermes = repo_root.join("state/hermes_memory.json");
    let cache = repo_root.join("state/query_cache.json");
    match (hermes.exists(), cache.exists()) {
        (true, true) => "Hermes memory and query cache found".to_string(),
        (true, false) => "Hermes memory found; query cache missing".to_string(),
        (false, true) => "Query cache found; Hermes memory missing".to_string(),
        (false, false) => "Local memory files not found yet".to_string(),
    }
}

fn launcher_status(state: &SharedLauncher) -> LauncherStatus {
    let mut services = Vec::new();
    let mut any_running = false;
    if let Ok(mut managed) = state.services.lock() {
        for key in ["backend", "rag", "agent"] {
            if let Some(service) = managed.get_mut(key) {
                let mut running = false;
                let mut pid = None;
                if let Some(child) = service.child.as_mut() {
                    match child.try_wait() {
                        Ok(None) => {
                            running = true;
                            pid = Some(child.id());
                        }
                        Ok(Some(_)) | Err(_) => {
                            service.child = None;
                        }
                    }
                }
                let detail = match service.name {
                    "backend" => {
                        if port_open(8000) {
                            running = true;
                            "API reachable at 127.0.0.1:8000".to_string()
                        } else {
                            "API port 8000 is closed".to_string()
                        }
                    }
                    "rag" => {
                        if port_open(6333) {
                            running = true;
                            "Qdrant reachable at 127.0.0.1:6333".to_string()
                        } else {
                            "Qdrant port 6333 is closed".to_string()
                        }
                    }
                    "agent" => {
                        if running {
                            "Agent swarm supervisor process is alive".to_string()
                        } else if port_open(8000) {
                            "Agent routes are hosted by backend API".to_string()
                        } else {
                            "Agent swarm is stopped".to_string()
                        }
                    }
                    _ => String::new(),
                };
                any_running = any_running || running;
                services.push(ServiceStatus {
                    name: service.name.to_string(),
                    label: service.label.to_string(),
                    status: if running { "running" } else { "stopped" }.to_string(),
                    detail,
                    pid,
                });
            }
        }
    }

    services.push(ServiceStatus {
        name: "memory".to_string(),
        label: "Memory System".to_string(),
        status: if state.repo_root.join("state/hermes_memory.json").exists() {
            "running"
        } else {
            "stopped"
        }
        .to_string(),
        detail: memory_detail(&state.repo_root),
        pid: None,
    });
    services.push(ServiceStatus {
        name: "frontend".to_string(),
        label: "Desktop Frontend".to_string(),
        status: "running".to_string(),
        detail: "Tauri dashboard process is active".to_string(),
        pid: None,
    });

    LauncherStatus {
        services,
        running: any_running,
    }
}

fn start_all(state: &SharedLauncher, app: &AppHandle) -> Result<LauncherStatus, String> {
    start_service(state, app, "rag")?;
    start_service(state, app, "backend")?;
    start_service(state, app, "agent")?;
    Ok(launcher_status(state))
}

fn stop_all(state: &SharedLauncher, app: &AppHandle) -> Result<LauncherStatus, String> {
    stop_service(state, app, "agent")?;
    stop_service(state, app, "backend")?;
    stop_service(state, app, "rag")?;
    Ok(launcher_status(state))
}

#[tauri::command]
fn start_anubis(state: State<'_, SharedLauncher>, app: AppHandle) -> Result<LauncherStatus, String> {
    start_all(&state, &app)
}

#[tauri::command]
fn stop_anubis(state: State<'_, SharedLauncher>, app: AppHandle) -> Result<LauncherStatus, String> {
    stop_all(&state, &app)
}

#[tauri::command]
fn restart_anubis(state: State<'_, SharedLauncher>, app: AppHandle) -> Result<LauncherStatus, String> {
    let _ = stop_all(&state, &app);
    start_all(&state, &app)
}

#[tauri::command]
fn get_anubis_status(state: State<'_, SharedLauncher>) -> LauncherStatus {
    launcher_status(&state)
}

#[tauri::command]
fn get_anubis_logs(state: State<'_, SharedLauncher>) -> Vec<LogLine> {
    state
        .logs
        .lock()
        .map(|logs| logs.iter().cloned().collect())
        .unwrap_or_default()
}

fn main() {
    tauri::Builder::default()
        .manage(Arc::new(LauncherState::new(repo_root())))
        .invoke_handler(tauri::generate_handler![
            start_anubis,
            stop_anubis,
            restart_anubis,
            get_anubis_status,
            get_anubis_logs
        ])
        .setup(|app| {
            let state = app.state::<SharedLauncher>();
            push_log(
                &state,
                app.handle(),
                "launcher",
                "system",
                format!("repo root: {}", state.repo_root.display()),
            );
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Anubis Desktop");
}
