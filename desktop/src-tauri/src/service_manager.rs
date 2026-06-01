use serde::Serialize;
use std::{
    collections::{HashMap, VecDeque},
    io::{BufRead, BufReader},
    net::{TcpStream, ToSocketAddrs},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, State};

const LOG_LIMIT: usize = 1_200;
const BACKEND_PORT: u16 = 8000;
const QDRANT_PORT: u16 = 6333;
const REDIS_PORT: u16 = 6379;
const SERVICE_STARTUP_GRACE: Duration = Duration::from_secs(15);

#[derive(Clone, Serialize)]
pub struct ServiceStatus {
    name: String,
    label: String,
    status: String,
    detail: String,
    pid: Option<u32>,
    restart_count: u32,
    last_failure: Option<String>,
    heartbeat_age_ms: Option<u64>,
}

#[derive(Clone, Serialize)]
pub struct LauncherStatus {
    services: Vec<ServiceStatus>,
    running: bool,
    healthy: bool,
}

#[derive(Clone, Serialize)]
pub struct LogLine {
    service: String,
    stream: String,
    line: String,
}

struct ManagedService {
    name: &'static str,
    label: &'static str,
    command: String,
    child: Option<Child>,
    desired: bool,
    restart_count: u32,
    last_failure: Option<String>,
    started_at: Option<Instant>,
    last_heartbeat: Option<Instant>,
}

impl ManagedService {
    fn new(name: &'static str, label: &'static str, command: String) -> Self {
        Self {
            name,
            label,
            command,
            child: None,
            desired: false,
            restart_count: 0,
            last_failure: None,
            started_at: None,
            last_heartbeat: None,
        }
    }
}

pub struct LauncherState {
    pub repo_root: PathBuf,
    pub(crate) services: Mutex<HashMap<&'static str, ManagedService>>,
    logs: Mutex<VecDeque<LogLine>>,
}

pub type SharedLauncher = Arc<LauncherState>;

impl LauncherState {
    pub fn new() -> Self {
        let repo_root = repo_root();
        let python = python_command(&repo_root);
        let mut services = HashMap::new();
        services.insert(
            "rag",
            ManagedService::new(
                "rag",
                "RAG / Qdrant",
                "docker compose up --no-color qdrant redis".to_string(),
            ),
        );
        services.insert(
            "backend",
            ManagedService::new(
                "backend",
                "Backend API",
                format!(
                    "{python} -m uvicorn backend.main:app --host 127.0.0.1 --port {BACKEND_PORT}"
                ),
            ),
        );
        services.insert(
            "agent",
            ManagedService::new(
                "agent",
                "Agent Orchestrator",
                format!(
                    "{python} -u -c 'from agent.multi_agent import AGENT_SPECS; print(\"agent orchestrator ready: %s agents\" % len(AGENT_SPECS), flush=True); import time\nwhile True: time.sleep(3600)'"
                ),
            ),
        );

        Self {
            repo_root,
            services: Mutex::new(services),
            logs: Mutex::new(VecDeque::with_capacity(LOG_LIMIT)),
        }
    }

    pub fn log(&self, app: &AppHandle, service: &str, stream: &str, line: String) {
        let event = LogLine {
            service: service.to_string(),
            stream: stream.to_string(),
            line,
        };
        if let Ok(mut logs) = self.logs.lock() {
            if logs.len() >= LOG_LIMIT {
                logs.pop_front();
            }
            logs.push_back(event.clone());
        }
        let _ = app.emit("anubis-log", event);
    }
}

#[derive(Clone, Serialize)]
pub(crate) struct WatchdogEvent {
    service: String,
    severity: String,
    message: String,
    restart_count: u32,
}

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

fn python_command(repo_root: &Path) -> String {
    let venv_python = repo_root.join(".venv/bin/python");
    if venv_python.exists() {
        venv_python.display().to_string()
    } else {
        "python3".to_string()
    }
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
                Ok(text) => state.log(&app, service, stream, text),
                Err(error) => {
                    state.log(&app, service, stream, format!("log stream closed: {error}"));
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

pub(crate) fn start_service(state: &SharedLauncher, app: &AppHandle, service_name: &'static str) -> Result<(), String> {
    let command = {
        let mut services = state.services.lock().map_err(|_| "service lock poisoned".to_string())?;
        let service = services
            .get_mut(service_name)
            .ok_or_else(|| format!("unknown service: {service_name}"))?;
        if let Some(child) = service.child.as_mut() {
            if child.try_wait().map_err(|error| error.to_string())?.is_none() {
                service.desired = true;
                state.log(app, service_name, "system", "already running".to_string());
                return Ok(());
            }
            service.child = None;
        }
        service.desired = true;
        service.command.clone()
    };

    state.log(app, service_name, "system", format!("starting: {command}"));
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
        service.started_at = Some(Instant::now());
        service.last_heartbeat = Some(Instant::now());
        service.last_failure = None;
    }
    state.log(app, service_name, "system", format!("started pid={pid}"));
    Ok(())
}

fn terminate_child(state: &SharedLauncher, app: &AppHandle, service_name: &str, process: &mut Child) {
    let pid = process.id();
    let _ = Command::new("bash")
        .arg("-lc")
        .arg(format!("pkill -TERM -P {pid} 2>/dev/null || true; kill -TERM {pid} 2>/dev/null || true"))
        .status();

    let started = Instant::now();
    while started.elapsed() < Duration::from_secs(5) {
        match process.try_wait() {
            Ok(Some(_)) => return,
            Ok(None) => thread::sleep(Duration::from_millis(120)),
            Err(error) => {
                state.log(app, service_name, "stderr", format!("stop check failed: {error}"));
                return;
            }
        }
    }

    state.log(
        app,
        service_name,
        "stderr",
        "graceful stop timed out; forcing shutdown".to_string(),
    );
    let _ = process.kill();
}

fn stop_service(state: &SharedLauncher, app: &AppHandle, service_name: &'static str) -> Result<(), String> {
    let mut child = {
        let mut services = state.services.lock().map_err(|_| "service lock poisoned".to_string())?;
        let service = services
            .get_mut(service_name)
            .ok_or_else(|| format!("unknown service: {service_name}"))?;
        service.desired = false;
        service.child.take()
    };

    if let Some(mut process) = child.take() {
        state.log(app, service_name, "system", "stopping".to_string());
        terminate_child(state, app, service_name, &mut process);
        let _ = process.wait();
        state.log(app, service_name, "system", "stopped".to_string());
    }

    if service_name == "rag" {
        run_stop_command(state, app, service_name, "docker compose stop qdrant redis");
    }

    Ok(())
}

pub(crate) fn restart_service(state: &SharedLauncher, app: &AppHandle, service_name: &'static str) -> Result<(), String> {
    let mut child = {
        let mut services = state.services.lock().map_err(|_| "service lock poisoned".to_string())?;
        let service = services
            .get_mut(service_name)
            .ok_or_else(|| format!("unknown service: {service_name}"))?;
        service.child.take()
    };

    if let Some(mut process) = child.take() {
        state.log(app, service_name, "watchdog", "restarting existing process".to_string());
        terminate_child(state, app, service_name, &mut process);
        let _ = process.wait();
    }

    start_service(state, app, service_name)
}

fn run_stop_command(state: &SharedLauncher, app: &AppHandle, service_name: &str, command: &str) {
    match shell_command(command, &state.repo_root).output() {
        Ok(result) => {
            let stdout = String::from_utf8_lossy(&result.stdout).trim().to_string();
            let stderr = String::from_utf8_lossy(&result.stderr).trim().to_string();
            if !stdout.is_empty() {
                state.log(app, service_name, "stdout", stdout);
            }
            if !stderr.is_empty() {
                state.log(app, service_name, "stderr", stderr);
            }
        }
        Err(error) => state.log(
            app,
            service_name,
            "stderr",
            format!("stop command failed: {error}"),
        ),
    }
}

pub(crate) fn port_open(port: u16) -> bool {
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

fn process_running(service: &mut ManagedService) -> (bool, Option<u32>) {
    if let Some(child) = service.child.as_mut() {
        match child.try_wait() {
            Ok(None) => return (true, Some(child.id())),
            Ok(Some(status)) => {
                service.last_failure = Some(format!("process exited with {status}"));
                service.child = None;
            }
            Err(error) => {
                service.last_failure = Some(format!("process status check failed: {error}"));
                service.child = None;
            }
        }
    }
    (false, None)
}

fn heartbeat_age_ms(service: &ManagedService) -> Option<u64> {
    service
        .last_heartbeat
        .map(|heartbeat| heartbeat.elapsed().as_millis().min(u128::from(u64::MAX)) as u64)
}

fn launcher_status(state: &SharedLauncher) -> LauncherStatus {
    let backend_open = port_open(BACKEND_PORT);
    let qdrant_open = port_open(QDRANT_PORT);
    let redis_open = port_open(REDIS_PORT);
    let mut services = Vec::new();
    let mut process_any_running = false;

    if let Ok(mut managed) = state.services.lock() {
        for key in ["rag", "backend", "agent"] {
            if let Some(service) = managed.get_mut(key) {
                let (mut running, pid) = process_running(service);
                let detail = match service.name {
                    "backend" => {
                        if backend_open {
                            running = true;
                            format!("FastAPI reachable at 127.0.0.1:{BACKEND_PORT}")
                        } else {
                            format!("FastAPI port {BACKEND_PORT} is closed")
                        }
                    }
                    "rag" => {
                        if qdrant_open {
                            running = true;
                            if redis_open {
                                format!("Qdrant:{QDRANT_PORT} and Redis:{REDIS_PORT} reachable")
                            } else {
                                format!("Qdrant:{QDRANT_PORT} reachable; Redis:{REDIS_PORT} closed")
                            }
                        } else {
                            format!("Qdrant port {QDRANT_PORT} is closed")
                        }
                    }
                    "agent" => {
                        if running {
                            "Multi-agent supervisor process is alive".to_string()
                        } else if backend_open {
                            "Agent routes are hosted by backend API".to_string()
                        } else {
                            "Agent orchestrator is stopped".to_string()
                        }
                    }
                    _ => String::new(),
                };
                process_any_running = process_any_running || running;
                if running {
                    service.last_heartbeat = Some(Instant::now());
                }
                services.push(ServiceStatus {
                    name: service.name.to_string(),
                    label: service.label.to_string(),
                    status: if running { "running" } else { "stopped" }.to_string(),
                    detail,
                    pid,
                    restart_count: service.restart_count,
                    last_failure: service.last_failure.clone(),
                    heartbeat_age_ms: heartbeat_age_ms(service),
                });
            }
        }
    }

    let memory_running = state.repo_root.join("state/hermes_memory.json").exists()
        || state.repo_root.join("state/query_cache.json").exists();
    services.push(ServiceStatus {
        name: "memory".to_string(),
        label: "Memory System".to_string(),
        status: if memory_running { "running" } else { "stopped" }.to_string(),
        detail: memory_detail(&state.repo_root),
        pid: None,
        restart_count: 0,
        last_failure: None,
        heartbeat_age_ms: None,
    });
    services.push(ServiceStatus {
        name: "frontend".to_string(),
        label: "Desktop Frontend".to_string(),
        status: "running".to_string(),
        detail: "Tauri dashboard process is active".to_string(),
        pid: None,
        restart_count: 0,
        last_failure: None,
        heartbeat_age_ms: None,
    });

    LauncherStatus {
        services,
        running: process_any_running,
        healthy: backend_open && qdrant_open,
    }
}

fn start_all(state: &SharedLauncher, app: &AppHandle) -> Result<LauncherStatus, String> {
    state.log(app, "launcher", "system", "starting Anubis services".to_string());
    start_service(state, app, "rag")?;
    start_service(state, app, "backend")?;
    start_service(state, app, "agent")?;
    Ok(launcher_status(state))
}

fn stop_all(state: &SharedLauncher, app: &AppHandle) -> Result<LauncherStatus, String> {
    state.log(app, "launcher", "system", "stopping Anubis services".to_string());
    stop_service(state, app, "agent")?;
    stop_service(state, app, "backend")?;
    stop_service(state, app, "rag")?;
    Ok(launcher_status(state))
}

#[tauri::command]
pub fn start_anubis(state: State<'_, SharedLauncher>, app: AppHandle) -> Result<LauncherStatus, String> {
    start_all(&state, &app)
}

#[tauri::command]
pub fn stop_anubis(state: State<'_, SharedLauncher>, app: AppHandle) -> Result<LauncherStatus, String> {
    stop_all(&state, &app)
}

#[tauri::command]
pub fn restart_anubis(state: State<'_, SharedLauncher>, app: AppHandle) -> Result<LauncherStatus, String> {
    let _ = stop_all(&state, &app);
    start_all(&state, &app)
}

#[tauri::command]
pub fn get_anubis_status(state: State<'_, SharedLauncher>) -> LauncherStatus {
    launcher_status(&state)
}

#[tauri::command]
pub fn get_anubis_logs(state: State<'_, SharedLauncher>) -> Vec<LogLine> {
    state
        .logs
        .lock()
        .map(|logs| logs.iter().cloned().collect())
        .unwrap_or_default()
}

pub(crate) fn check_service_health(
    state: &SharedLauncher,
    service_name: &'static str,
) -> Result<Option<String>, String> {
    let mut services = state.services.lock().map_err(|_| "service lock poisoned".to_string())?;
    let service = services
        .get_mut(service_name)
        .ok_or_else(|| format!("unknown service: {service_name}"))?;
    if !service.desired {
        return Ok(None);
    }

    let (process_alive, _) = process_running(service);
    if !process_alive {
        let reason = service
            .last_failure
            .clone()
            .unwrap_or_else(|| "process is not running".to_string());
        return Ok(Some(reason));
    }

    match service_name {
        "backend" => {
            if port_open(BACKEND_PORT) {
                service.last_heartbeat = Some(Instant::now());
                Ok(None)
            } else if service
                .started_at
                .is_some_and(|started| started.elapsed() < SERVICE_STARTUP_GRACE)
            {
                Ok(None)
            } else {
                let reason = format!("heartbeat failed: backend port {BACKEND_PORT} is closed");
                service.last_failure = Some(reason.clone());
                Ok(Some(reason))
            }
        }
        "agent" => {
            service.last_heartbeat = Some(Instant::now());
            Ok(None)
        }
        _ => Ok(None),
    }
}

pub(crate) fn record_watchdog_restart(
    state: &SharedLauncher,
    service_name: &'static str,
    reason: &str,
) -> u32 {
    let Ok(mut services) = state.services.lock() else {
        return 0;
    };
    let Some(service) = services.get_mut(service_name) else {
        return 0;
    };
    service.restart_count = service.restart_count.saturating_add(1);
    service.last_failure = Some(reason.to_string());
    service.restart_count
}

pub(crate) fn notify_watchdog(
    state: &SharedLauncher,
    app: &AppHandle,
    service: &str,
    severity: &str,
    message: String,
    restart_count: u32,
) {
    state.log(app, service, "watchdog", message.clone());
    let _ = app.emit(
        "anubis-watchdog",
        WatchdogEvent {
            service: service.to_string(),
            severity: severity.to_string(),
            message,
            restart_count,
        },
    );
}
