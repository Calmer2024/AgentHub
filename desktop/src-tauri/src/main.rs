use std::{
    fs,
    net::{TcpStream, ToSocketAddrs},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

use tauri::{path::BaseDirectory, Manager, WindowEvent};

const BACKEND_PORT: u16 = 8188;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct BackendState(Mutex<Option<Child>>);

fn main() {
    tauri::Builder::default()
        .manage(BackendState(Mutex::new(None)))
        .setup(|app| {
            let state = app.state::<BackendState>();
            match spawn_backend(app) {
                Ok(child) => {
                    *state.0.lock().expect("backend state poisoned") = Some(child);
                }
                Err(error) => {
                    eprintln!("failed to start AgentHub backend: {error}");
                }
            }
            wait_for_backend(BACKEND_PORT);
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) {
                let child = {
                    let state = window.app_handle().state::<BackendState>();
                    let child = state.0.lock().expect("backend state poisoned").take();
                    child
                };
                if let Some(mut child) = child {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("failed to run AgentHub local desktop shell");
}

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

fn wait_for_backend(port: u16) {
    let address = format!("127.0.0.1:{port}");
    let Ok(mut addrs) = address.to_socket_addrs() else {
        return;
    };
    let Some(addr) = addrs.next() else {
        return;
    };

    for _ in 0..40 {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(200)).is_ok() {
            return;
        }
        thread::sleep(Duration::from_millis(250));
    }
}
