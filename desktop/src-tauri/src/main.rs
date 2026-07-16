#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    env,
    net::{TcpStream, ToSocketAddrs},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

#[cfg(not(debug_assertions))]
use std::fs;

#[cfg(not(debug_assertions))]
use tauri::path::BaseDirectory;
use tauri::{Manager, WindowEvent};

const BACKEND_PORT: u16 = 8188;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct BackendState(Mutex<Option<Child>>);

fn main() {
    tauri::Builder::default()
        .manage(BackendState(Mutex::new(None)))
        .setup(|_app| {
            #[cfg(not(debug_assertions))]
            {
                let state = _app.state::<BackendState>();
                let child = spawn_backend(_app)?;
                *state.0.lock().expect("backend state poisoned") = Some(child);
            }

            let backend_port = development_backend_port();
            wait_for_backend(backend_port)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) {
                let child = {
                    let state = window.app_handle().state::<BackendState>();
                    let child = state.0.lock().expect("backend state poisoned").take();
                    child
                };
                if let Some(child) = child {
                    terminate_backend(child);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("failed to run AgentHub local desktop shell");
}

#[cfg(not(debug_assertions))]
fn spawn_backend(app: &tauri::App) -> Result<Child, Box<dyn std::error::Error>> {
    let backend = app
        .path()
        .resolve("resources/agenthub-backend.exe", BaseDirectory::Resource)?;
    let data_dir = app.path().app_data_dir()?;
    fs::create_dir_all(&data_dir)?;

    let mut command = Command::new(backend);
    command
        .env("AGENTHUB_DESKTOP_PORT", BACKEND_PORT.to_string())
        .env("AGENTHUB_DESKTOP_DATA_DIR", data_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let child = command.spawn()?;

    Ok(child)
}

fn development_backend_port() -> u16 {
    if cfg!(debug_assertions) {
        return env::var("AGENTHUB_DEV_BACKEND_PORT")
            .ok()
            .and_then(|value| value.parse::<u16>().ok())
            .unwrap_or(BACKEND_PORT);
    }
    BACKEND_PORT
}

#[cfg(windows)]
fn terminate_backend(child: Child) {
    use std::os::windows::process::CommandExt;

    let pid = child.id().to_string();
    let _ = Command::new("taskkill")
        .args(["/PID", pid.as_str(), "/T", "/F"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .creation_flags(CREATE_NO_WINDOW)
        .status();
}

#[cfg(not(windows))]
fn terminate_backend(mut child: Child) {
    let _ = child.kill();
}

fn wait_for_backend(port: u16) -> Result<(), Box<dyn std::error::Error>> {
    let address = format!("127.0.0.1:{port}");
    let Ok(mut addrs) = address.to_socket_addrs() else {
        return Err(format!("cannot resolve backend address: {address}").into());
    };
    let Some(addr) = addrs.next() else {
        return Err(format!("backend address has no socket target: {address}").into());
    };

    for _ in 0..40 {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(200)).is_ok() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(250));
    }
    Err(format!("timed out waiting for AgentHub backend at {address}").into())
}
