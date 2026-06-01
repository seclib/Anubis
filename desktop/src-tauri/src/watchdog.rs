use std::{thread, time::Duration};
use tauri::AppHandle;

use crate::service_manager::{
    check_service_health, notify_watchdog, record_watchdog_restart, restart_service, SharedLauncher,
};

const WATCHDOG_INTERVAL: Duration = Duration::from_secs(3);
const WATCHED_SERVICES: [&str; 2] = ["backend", "agent"];

pub fn spawn_watchdog(state: SharedLauncher, app: AppHandle) {
    thread::spawn(move || {
        state.log(&app, "watchdog", "system", "self-healing watchdog started".to_string());
        loop {
            thread::sleep(WATCHDOG_INTERVAL);
            for service in WATCHED_SERVICES {
                let service_name = match service {
                    "backend" => "backend",
                    "agent" => "agent",
                    _ => continue,
                };

                let failure = match check_service_health(&state, service_name) {
                    Ok(failure) => failure,
                    Err(error) => {
                        notify_watchdog(
                            &state,
                            &app,
                            service_name,
                            "error",
                            format!("watchdog check failed: {error}"),
                            0,
                        );
                        continue;
                    }
                };

                let Some(reason) = failure else {
                    continue;
                };

                let restart_count = record_watchdog_restart(&state, service_name, &reason);
                notify_watchdog(
                    &state,
                    &app,
                    service_name,
                    "warning",
                    format!("failure detected: {reason}; restarting"),
                    restart_count,
                );

                if let Err(error) = restart_service(&state, &app, service_name) {
                    notify_watchdog(
                        &state,
                        &app,
                        service_name,
                        "error",
                        format!("restart failed: {error}"),
                        restart_count,
                    );
                } else {
                    notify_watchdog(
                        &state,
                        &app,
                        service_name,
                        "info",
                        "restart completed".to_string(),
                        restart_count,
                    );
                }
            }
        }
    });
}
