# Core Concepts

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](core-concepts.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](../pt-BR/core-concepts.md)

## Plant

A plant is the main execution unit in Senamby. It groups:

- variables
- one driver instance
- zero or more controller instances
- sample time
- live session state such as connected, paused, stats, and runtime status

In day-to-day usage, a plant is what you open, connect, monitor, export, close, and remove in the `Plotter` module.

## Variable

A variable describes a signal in the plant.

- `sensor`: a measured process value, usually charted with PV and SP
- `atuador`: an actuator/output value, usually charted as the manipulated variable

Important note:

- the UI refers to actuators in user-facing language
- the persisted type value is currently `atuador`

Each variable has:

- `id`
- `name`
- `unit`
- `setpoint`
- `pv_min`
- `pv_max`
- optional linked sensor ids for actuator-to-sensor relationships

## Driver Plugin vs Driver Instance

A **driver plugin** is the reusable definition stored in the plugins catalog.

A **driver instance** is the selected plugin plus the configuration attached to one plant.

The driver is responsible for:

- opening and closing external connections
- reading sensors
- optionally reading actuator feedback
- writing actuator outputs when controllers are active
- converting raw device units into public plant units

At runtime, the driver receives:

- `context.config`
- `context.plant`

Required methods:

- `connect()`
- `stop()`
- `read()`

`write(outputs)` becomes required when the plant has active controllers.

## Controller Plugin vs Controller Instance

A **controller plugin** is the reusable control algorithm stored in the plugins catalog.

A **controller instance** is the configured controller attached to one plant, including:

- activation state
- input bindings
- output bindings
- parameter values
- runtime status

At runtime, the controller receives:

- `context.controller`
- `context.plant`

Required method:

- `compute(snapshot)`

Current runtime statuses shown in the app:

- `synced`: the saved configuration is already applied to the running runtime
- `pending_restart`: the configuration is saved, but the runtime must reconnect before it can use it

## Runtime

The runtime exists only while a plant is connected. It runs the live cycle:

`read -> control -> write -> publish`

The frontend does not execute this loop. The frontend only reacts to status and telemetry events emitted by the backend.

Important session rules:

- connecting starts the runtime
- disconnecting stops the runtime but keeps the plant open in the session
- pausing only pauses plotting in the UI; the runtime keeps running
- closing unloads the plant from the session
- removing deletes the persisted plant registry

## Hot Update

While a plant is connected, Senamby can try to apply controller changes live.

Typical outcomes:

- parameter or binding changes may be applied immediately
- environment-sensitive changes may become `pending_restart`
- removal of an active synced controller is blocked until it is deactivated

## Workspace

The workspace is the persistent storage area for:

- plugins
- plants
- Python environments
- runtime bootstrap/session artifacts

By default it lives under:

`Documents/Senamby/workspace`

Important distinction:

- the workspace is persistent storage
- the current session only contains plants loaded in the UI
- persisted plants are not automatically reopened at startup

## Export and Analyzer

Live plotter sessions can be exported as:

- CSV for spreadsheet or script-based processing
- JSON for structured replay in the Analyzer

The Analyzer is an offline module. It reads exported JSON files and rebuilds sensor, setpoint, and linked actuator series without connecting to a live runtime.
