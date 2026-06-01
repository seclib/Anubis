mod service_manager;
mod watchdog;

use service_manager::{
    get_anubis_logs, get_anubis_status, restart_anubis, start_anubis, stop_anubis, LauncherState,
    SharedLauncher,
};
use std::sync::Arc;
use tauri::{Emitter, Manager};

fn main() {
    tauri::Builder::default()
        .manage(Arc::new(LauncherState::new()))
        .invoke_handler(tauri::generate_handler![
            start_anubis,
            stop_anubis,
            restart_anubis,
            get_anubis_status,
            get_anubis_logs
        ])
        .setup(|app| {
            let state = app.state::<SharedLauncher>();
            state.log(
                app.handle(),
                "launcher",
                "system",
                format!("repo root: {}", state.repo_root.display()),
            );
            watchdog::spawn_watchdog(state.inner().clone(), app.handle().clone());
            let _ = app.emit("anubis-ready", get_anubis_status(state));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Anubis Desktop");
}
