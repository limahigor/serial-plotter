use super::{
    environment::prepare_python_command, RuntimeCyclePhase, RuntimeEnvelope, RuntimeLifecycleState,
    RuntimeStatusEvent, RuntimeTelemetryEvent, RuntimeTelemetryPayload, SharedHandshake,
    SharedMetrics,
};
use crate::core::error::{AppError, AppResult};
use crate::core::models::console::{
    ConsoleLogInput, ConsoleLogLevel, ConsoleSourceKind, ConsoleSourceScope,
};
use crate::core::services::console::ConsoleService;
use crate::state::ConsoleStore;
use parking_lot::Mutex;
use serde::Deserialize;
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStderr, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Runtime};

#[allow(clippy::cast_precision_loss)]
fn sample_time_ms_as_f64(sample_time_ms: u64) -> f64 {
    sample_time_ms as f64
}

pub(super) fn spawn_driver_process(
    venv_python_path: &std::path::Path,
    runner_path: &std::path::Path,
    runtime_dir: &std::path::Path,
    bootstrap_path: &std::path::Path,
) -> AppResult<Child> {
    let mut command = Command::new(venv_python_path);
    prepare_python_command(
        command
            .arg("-u")
            .arg(runner_path)
            .arg("--runtime-dir")
            .arg(runtime_dir)
            .arg("--bootstrap")
            .arg(bootstrap_path),
    );
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    command.spawn().map_err(|error| {
        AppError::IoError(format!(
            "Falha ao iniciar processo Python do driver '{}': {error}",
            venv_python_path.display()
        ))
    })
}

pub(super) fn spawn_stdout_task<R: Runtime + 'static>(
    app: AppHandle<R>,
    console: Arc<ConsoleStore>,
    plant_id: String,
    plant_name: String,
    runtime_id: String,
    configured_sample_time_ms: u64,
    stdout: ChildStdout,
    handshake: SharedHandshake,
    metrics: SharedMetrics,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            let line = match line {
                Ok(line) => line,
                Err(error) => {
                    let _ = emit_error_event(
                        &app,
                        &plant_id,
                        &runtime_id,
                        &format!("Falha ao ler stdout do driver: {error}"),
                    );
                    append_plant_console_log(
                        &app,
                        console.as_ref(),
                        &plant_id,
                        &plant_name,
                        &runtime_id,
                        ConsoleLogLevel::Error,
                        ConsoleSourceKind::Runtime,
                        &format!("Falha ao ler stdout do driver: {error}"),
                        None,
                        None,
                        None,
                        None,
                        None,
                    );
                    break;
                }
            };

            let envelope = match serde_json::from_str::<RuntimeEnvelope>(&line) {
                Ok(message) => message,
                Err(error) => {
                    let _ = emit_error_event(
                        &app,
                        &plant_id,
                        &runtime_id,
                        &format!("Mensagem inválida recebida do driver: {error}"),
                    );
                    append_plant_console_log(
                        &app,
                        console.as_ref(),
                        &plant_id,
                        &plant_name,
                        &runtime_id,
                        ConsoleLogLevel::Error,
                        ConsoleSourceKind::Runtime,
                        &format!("Mensagem inválida recebida do driver: {error}"),
                        None,
                        None,
                        None,
                        None,
                        Some(json!({ "raw_line": line })),
                    );
                    continue;
                }
            };

            match envelope.msg_type.as_str() {
                "ready" => handle_ready_event(
                    &app,
                    &plant_id,
                    &runtime_id,
                    configured_sample_time_ms,
                    &handshake,
                    &metrics,
                ),
                "connected" => handle_connected_event(
                    &app,
                    &plant_id,
                    &runtime_id,
                    configured_sample_time_ms,
                    &handshake,
                    &metrics,
                ),
                "error" => handle_runtime_error_event(
                    &app,
                    &plant_id,
                    &runtime_id,
                    &plant_name,
                    configured_sample_time_ms,
                    &envelope.payload,
                    &handshake,
                    &metrics,
                    console.as_ref(),
                ),
                "warning" => handle_runtime_warning_event(
                    &app,
                    console.as_ref(),
                    &plant_id,
                    &plant_name,
                    &runtime_id,
                    &envelope.payload,
                ),
                "log" => handle_runtime_log_event(
                    &app,
                    console.as_ref(),
                    &plant_id,
                    &plant_name,
                    &runtime_id,
                    &envelope.payload,
                ),
                "telemetry" => process_telemetry(
                    &app,
                    &plant_id,
                    &runtime_id,
                    configured_sample_time_ms,
                    envelope.payload,
                    &metrics,
                ),
                "cycle_overrun" => {
                    let mut lock = metrics.lock();
                    lock.cycle_late = true;
                    lock.late_cycle_count = lock.late_cycle_count.saturating_add(1);
                }
                "stopped" => {
                    handle_stopped_event(
                        &app,
                        &plant_id,
                        &runtime_id,
                        configured_sample_time_ms,
                        &metrics,
                    );
                    break;
                }
                _ => {}
            }
        }
    })
}

pub(super) fn spawn_stderr_task<R: Runtime + 'static>(
    app: AppHandle<R>,
    console: Arc<ConsoleStore>,
    plant_id: String,
    plant_name: String,
    runtime_id: String,
    stderr: ChildStderr,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines().map_while(Result::ok) {
            if !line.trim().is_empty() {
                eprintln!("[driver-runtime][plant={plant_id}][runtime={runtime_id}] {line}");
                append_plant_console_log(
                    &app,
                    console.as_ref(),
                    &plant_id,
                    &plant_name,
                    &runtime_id,
                    infer_stderr_log_level(&line),
                    ConsoleSourceKind::NativeOutput,
                    &line,
                    None,
                    None,
                    None,
                    None,
                    Some(json!({
                        "channel": "stderr",
                        "classification": "external_output",
                        "source_label": "EXTERNO"
                    })),
                );
            }
        }
    })
}

#[derive(Debug, Default, Deserialize)]
struct RuntimeConsolePayload {
    #[serde(default)]
    level: Option<ConsoleLogLevel>,
    #[serde(default)]
    message: Option<String>,
    #[serde(default)]
    source_kind: Option<ConsoleSourceKind>,
    #[serde(default)]
    plugin_id: Option<String>,
    #[serde(default)]
    plugin_name: Option<String>,
    #[serde(default)]
    controller_id: Option<String>,
    #[serde(default)]
    controller_name: Option<String>,
    #[serde(default)]
    details: Option<Value>,
}

fn append_plant_console_log<R: Runtime>(
    app: &AppHandle<R>,
    console: &ConsoleStore,
    plant_id: &str,
    plant_name: &str,
    runtime_id: &str,
    level: ConsoleLogLevel,
    source_kind: ConsoleSourceKind,
    message: &str,
    plugin_id: Option<String>,
    plugin_name: Option<String>,
    controller_id: Option<String>,
    controller_name: Option<String>,
    details: Option<Value>,
) {
    let _ = ConsoleService::append_log(
        Some(app),
        console,
        ConsoleLogInput {
            level,
            message: message.to_string(),
            source_scope: ConsoleSourceScope::Plant,
            source_kind,
            plant_id: Some(plant_id.to_string()),
            plant_name: Some(plant_name.to_string()),
            runtime_id: Some(runtime_id.to_string()),
            plugin_id,
            plugin_name,
            controller_id,
            controller_name,
            details,
        },
    );
}

fn infer_stderr_log_level(_line: &str) -> ConsoleLogLevel {
    ConsoleLogLevel::Debug
}

fn handle_runtime_warning_event<R: Runtime>(
    app: &AppHandle<R>,
    console: &ConsoleStore,
    plant_id: &str,
    plant_name: &str,
    runtime_id: &str,
    payload: &Value,
) {
    let payload = serde_json::from_value::<RuntimeConsolePayload>(payload.clone()).unwrap_or_default();
    let message = payload
        .message
        .unwrap_or_else(|| "Aviso da runtime Python".to_string());
    append_plant_console_log(
        app,
        console,
        plant_id,
        plant_name,
        runtime_id,
        payload.level.unwrap_or(ConsoleLogLevel::Warning),
        payload.source_kind.unwrap_or(ConsoleSourceKind::Runtime),
        &message,
        payload.plugin_id,
        payload.plugin_name,
        payload.controller_id,
        payload.controller_name,
        payload.details,
    );
}

fn handle_runtime_log_event<R: Runtime>(
    app: &AppHandle<R>,
    console: &ConsoleStore,
    plant_id: &str,
    plant_name: &str,
    runtime_id: &str,
    payload: &Value,
) {
    let payload = serde_json::from_value::<RuntimeConsolePayload>(payload.clone()).unwrap_or_default();
    let message = payload
        .message
        .unwrap_or_else(|| "Log da runtime Python".to_string());
    append_plant_console_log(
        app,
        console,
        plant_id,
        plant_name,
        runtime_id,
        payload.level.unwrap_or(ConsoleLogLevel::Info),
        payload.source_kind.unwrap_or(ConsoleSourceKind::Runtime),
        &message,
        payload.plugin_id,
        payload.plugin_name,
        payload.controller_id,
        payload.controller_name,
        payload.details,
    );
}

fn handle_ready_event<R: Runtime>(
    app: &AppHandle<R>,
    plant_id: &str,
    runtime_id: &str,
    configured_sample_time_ms: u64,
    handshake: &SharedHandshake,
    metrics: &SharedMetrics,
) {
    {
        let mut lock = handshake.0.lock();
        lock.ready = true;
    }
    handshake.1.notify_all();

    let mut lock = metrics.lock();
    lock.lifecycle_state = RuntimeLifecycleState::Ready;
    emit_status_event(
        app,
        RuntimeStatusEvent {
            plant_id: plant_id.to_string(),
            runtime_id: runtime_id.to_string(),
            lifecycle_state: RuntimeLifecycleState::Ready,
            cycle_phase: RuntimeCyclePhase::CycleStarted,
            configured_sample_time_ms,
            effective_dt_ms: sample_time_ms_as_f64(configured_sample_time_ms),
            cycle_late: false,
        },
    );
}

fn handle_connected_event<R: Runtime>(
    app: &AppHandle<R>,
    plant_id: &str,
    runtime_id: &str,
    configured_sample_time_ms: u64,
    handshake: &SharedHandshake,
    metrics: &SharedMetrics,
) {
    {
        let mut lock = handshake.0.lock();
        lock.connected = true;
    }
    handshake.1.notify_all();

    let mut lock = metrics.lock();
    lock.lifecycle_state = RuntimeLifecycleState::Running;
    lock.cycle_phase = RuntimeCyclePhase::ReadInputs;
    emit_status_event(
        app,
        RuntimeStatusEvent {
            plant_id: plant_id.to_string(),
            runtime_id: runtime_id.to_string(),
            lifecycle_state: RuntimeLifecycleState::Running,
            cycle_phase: RuntimeCyclePhase::ReadInputs,
            configured_sample_time_ms,
            effective_dt_ms: sample_time_ms_as_f64(configured_sample_time_ms),
            cycle_late: false,
        },
    );
}

fn handle_runtime_error_event<R: Runtime>(
    app: &AppHandle<R>,
    plant_id: &str,
    plant_name: &str,
    runtime_id: &str,
    configured_sample_time_ms: u64,
    payload: &Value,
    handshake: &SharedHandshake,
    metrics: &SharedMetrics,
    console: &ConsoleStore,
) {
    let message = payload
        .get("message")
        .and_then(Value::as_str)
        .unwrap_or("Erro na runtime Python")
        .to_string();

    {
        let mut lock = handshake.0.lock();
        lock.error = Some(message.clone());
    }
    handshake.1.notify_all();

    let mut lock = metrics.lock();
    lock.lifecycle_state = RuntimeLifecycleState::Faulted;
    emit_status_event(
        app,
        RuntimeStatusEvent {
            plant_id: plant_id.to_string(),
            runtime_id: runtime_id.to_string(),
            lifecycle_state: RuntimeLifecycleState::Faulted,
            cycle_phase: lock.cycle_phase,
            configured_sample_time_ms,
            effective_dt_ms: lock.effective_dt_ms,
            cycle_late: lock.cycle_late,
        },
    );
    append_plant_console_log(
        app,
        console,
        plant_id,
        plant_name,
        runtime_id,
        ConsoleLogLevel::Error,
        ConsoleSourceKind::Runtime,
        &message,
        None,
        None,
        None,
        None,
        Some(payload.clone()),
    );
    let _ = emit_error_event(app, plant_id, runtime_id, &message);
}

fn handle_stopped_event<R: Runtime>(
    app: &AppHandle<R>,
    plant_id: &str,
    runtime_id: &str,
    configured_sample_time_ms: u64,
    metrics: &SharedMetrics,
) {
    let mut lock = metrics.lock();
    lock.lifecycle_state = RuntimeLifecycleState::Stopped;
    emit_status_event(
        app,
        RuntimeStatusEvent {
            plant_id: plant_id.to_string(),
            runtime_id: runtime_id.to_string(),
            lifecycle_state: RuntimeLifecycleState::Stopped,
            cycle_phase: RuntimeCyclePhase::SleepUntilDeadline,
            configured_sample_time_ms,
            effective_dt_ms: lock.effective_dt_ms,
            cycle_late: false,
        },
    );
}

fn process_telemetry<R: Runtime>(
    app: &AppHandle<R>,
    plant_id: &str,
    runtime_id: &str,
    configured_sample_time_ms: u64,
    payload: Value,
    metrics: &SharedMetrics,
) {
    let payload = match serde_json::from_value::<RuntimeTelemetryPayload>(payload) {
        Ok(payload) => payload,
        Err(error) => {
            let _ = emit_error_event(
                app,
                plant_id,
                runtime_id,
                &format!("Payload de telemetria inválido: {error}"),
            );
            return;
        }
    };

    let effective_dt_ms = if payload.effective_dt_ms.is_finite() {
        payload.effective_dt_ms
    } else {
        sample_time_ms_as_f64(configured_sample_time_ms)
    };
    let cycle_duration_ms = if payload.cycle_duration_ms.is_finite() {
        payload.cycle_duration_ms
    } else {
        0.0
    };
    let read_duration_ms = if payload.read_duration_ms.is_finite() {
        payload.read_duration_ms
    } else {
        0.0
    };
    let cycle_late = payload.cycle_late;

    {
        let mut lock = metrics.lock();
        lock.lifecycle_state = RuntimeLifecycleState::Running;
        lock.cycle_phase = RuntimeCyclePhase::PublishTelemetry;
        lock.effective_dt_ms = effective_dt_ms;
        lock.cycle_duration_ms = cycle_duration_ms;
        lock.read_duration_ms = read_duration_ms;
        lock.uptime_s = payload.uptime_s.max(0.0);
        lock.cycle_late = cycle_late;
        if cycle_late {
            lock.late_cycle_count = lock.late_cycle_count.saturating_add(1);
        }
        lock.last_telemetry_at = Some(
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|time| time.as_secs())
                .unwrap_or(0),
        );
    }

    let event = RuntimeTelemetryEvent {
        plant_id: plant_id.to_string(),
        runtime_id: runtime_id.to_string(),
        lifecycle_state: RuntimeLifecycleState::Running,
        cycle_phase: RuntimeCyclePhase::PublishTelemetry,
        timestamp: payload.timestamp,
        cycle_id: payload.cycle_id,
        configured_sample_time_ms,
        effective_dt_ms,
        cycle_duration_ms,
        read_duration_ms,
        control_duration_ms: payload.control_duration_ms,
        write_duration_ms: payload.write_duration_ms,
        publish_duration_ms: payload.publish_duration_ms,
        cycle_late,
        late_by_ms: payload.late_by_ms,
        phase: payload.phase,
        uptime_s: payload.uptime_s,
        sensors: payload.sensors,
        actuators: payload.actuators,
        actuators_read: payload.actuators_read,
        setpoints: payload.setpoints,
        controller_outputs: payload.controller_outputs,
        written_outputs: payload.written_outputs,
        controller_durations_ms: payload.controller_durations_ms,
    };
    let _ = app.emit("plant://telemetry", event);
}

pub(super) fn wait_for_handshake(handshake: &SharedHandshake, timeout: Duration) -> AppResult<()> {
    let deadline = Instant::now() + timeout;

    let mut guard = handshake.0.lock();
    loop {
        if guard.connected {
            return Ok(());
        }
        if let Some(message) = guard.error.clone() {
            return Err(AppError::IoError(format!(
                "Falha durante handshake da runtime: {message}"
            )));
        }

        let now = Instant::now();
        if now >= deadline {
            return Err(AppError::IoError(
                "Timeout aguardando handshake da runtime Python".into(),
            ));
        }

        let wait_for = deadline.saturating_duration_since(now);
        if handshake.1.wait_for(&mut guard, wait_for).timed_out() {
            return Err(AppError::IoError(
                "Timeout aguardando handshake da runtime Python".into(),
            ));
        }
    }
}

pub(super) fn send_command(
    stdin: &Arc<Mutex<ChildStdin>>,
    msg_type: &str,
    payload: Option<Value>,
) -> AppResult<()> {
    let mut writer = stdin.lock();
    let mut envelope = serde_json::Map::new();
    envelope.insert("type".to_string(), Value::String(msg_type.to_string()));
    if let Some(payload) = payload {
        envelope.insert("payload".to_string(), payload);
    }

    let line = serde_json::to_string(&envelope).map_err(|error| {
        AppError::IoError(format!("Falha ao serializar comando para runtime: {error}"))
    })?;
    writer.write_all(line.as_bytes()).map_err(|error| {
        AppError::IoError(format!("Falha ao enviar comando para runtime: {error}"))
    })?;
    writer.write_all(b"\n").map_err(|error| {
        AppError::IoError(format!("Falha ao finalizar comando para runtime: {error}"))
    })?;
    writer.flush().map_err(|error| {
        AppError::IoError(format!("Falha ao flush de comando para runtime: {error}"))
    })?;

    Ok(())
}

pub(super) fn emit_status_event<R: Runtime>(app: &AppHandle<R>, event: RuntimeStatusEvent) {
    let _ = app.emit("plant://status", event);
}

pub(super) fn emit_error_event<R: Runtime>(
    app: &AppHandle<R>,
    plant_id: &str,
    runtime_id: &str,
    message: &str,
) -> AppResult<()> {
    app.emit(
        "plant://error",
        json!({
            "plant_id": plant_id,
            "runtime_id": runtime_id,
            "message": message,
        }),
    )
    .map_err(|error| AppError::IoError(format!("Falha ao emitir evento de erro: {error}")))?;

    Ok(())
}
