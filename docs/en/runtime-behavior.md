# Runtime Behavior

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](runtime-behavior.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](../pt-BR/runtime-behavior.md)

## Connect Flow

When a plant connects, the backend:

1. resolves the saved driver and active controllers
2. refreshes plugin metadata from the workspace when needed
3. prepares or reuses the Python environment
4. builds a compact bootstrap payload
5. starts the Python runner
6. waits for `ready` and `connected` handshake messages
7. begins forwarding live status and telemetry to the frontend

## Runtime Communication Channels

The runtime process uses three channels:

- `stdin`: commands from Rust to the runner
- `stdout`: internal JSON protocol from the runner back to Rust
- `stderr`: logs, tracebacks, and redirected native output

Important behavior:

- the runner reserves `stdout` for JSON protocol traffic
- the runner duplicates the original `stdout` descriptor for protocol writes
- Python `print()` output is redirected to `stderr`
- common native library `stdout` output is also redirected to `stderr`
- `context.logger` in drivers/controllers emits structured log events for the Console module

## Live Runtime Rules

- the runtime exists only while the plant is connected
- plants are not auto-loaded on startup
- controllers can be hot-updated while connected
- some controller changes may require reconnect and become `pending_restart`

## Cycle: `read -> control -> write -> publish`

### 1. Read

The runner calls `driver.read()` and expects:

```json
{
  "sensors": { "sensor_1": 58.2 },
  "actuators": { "actuator_1": 37.0 }
}
```

### 2. Control

For each active controller, the runner builds a snapshot with:

- `dt_s`
- `setpoints`
- `sensors`
- `actuators`
- `variables_by_id`
- `controller`

Then it calls `compute(snapshot)` and receives:

```json
{
  "actuator_1": 42.0
}
```

### 3. Write

The runner merges cycle outputs and calls:

```python
driver.write(outputs)
```

### 4. Publish

The runner publishes telemetry to the backend, which forwards it to the frontend as `plant://telemetry`.

## Pause Backlog

Pause does not stop the runtime loop. The frontend stops plotting temporarily and accumulates telemetry backlog. On resume, the queued telemetry is replayed into the charts.

This means:

- control keeps running
- driver reads and writes continue
- only chart rendering is paused in the UI

## Telemetry and Plotting

The backend emits flat `plant://telemetry` events to the frontend.

Important plotting rule:

- actuator charts currently use actuator readback from telemetry
- they do not plot the raw outgoing write payload as the main displayed actuator value

Telemetry can include fields such as:

- `cycle_id`
- `configured_sample_time_ms`
- `effective_dt_ms`
- `cycle_duration_ms`
- `read_duration_ms`
- `control_duration_ms`
- `write_duration_ms`
- `publish_duration_ms`
- `cycle_late`
- `late_by_ms`
- `sensors`
- `actuators`
- `actuators_read`
- `setpoints`
- `controller_outputs`
- `written_outputs`

## Hot Update and `pending_restart`

When controller configuration changes while the plant is connected:

- Senamby tries to hot-load the updated controller set
- if the current runtime/environment can accept the change, status stays `synced`
- if the change requires environment rebuild or reconnect, status becomes `pending_restart`

Typical fix for `pending_restart`:

1. save the controller change
2. disconnect the plant
3. reconnect the plant

## Runtime Files

Persistent workspace data lives under:

- `drivers/`
- `controllers/`
- `plants/`
- `envs/`

Connected runtime sessions also use:

- `runtimes/<runtime_id>/bootstrap.json`

The Python runner script is stored under the shared runtimes area and reused across runtime sessions.

## Debugging Notes

- Python errors and logs arrive on `stderr`
- the backend echoes `stderr` lines with the `driver-runtime` prefix
- structured driver/controller logs are also forwarded to the Console
- if a native library bypasses the process handles entirely, protocol corruption is still theoretically possible, but it is no longer the common case for ordinary `printf`-style output
