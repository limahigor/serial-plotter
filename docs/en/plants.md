# Plants

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](plants.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](../pt-BR/plants.md)

## Creating a Plant Step by Step

When creating a plant in the `Plotter` module, work through these sections in order.

### 1. Plant identity

Define:

- plant name
- sample time in milliseconds

### 2. Variables

Add the variables that describe the public process model.

Use:

- `sensor` for measured values
- `atuador` for actuator/output values

For each variable, set:

- display name
- engineering unit
- default setpoint
- minimum and maximum public range

Actuators can be linked to one or more sensors for UI grouping and controller binding purposes.

### 3. Driver instance

Choose the driver plugin the plant will use and fill the instance configuration required by that plugin's schema.

### 4. Controller instances

Optionally add one or more controllers and configure:

- controller display name
- active/inactive state
- input variable bindings
- output variable bindings
- parameter values

## Importing or Opening a Plant

Senamby supports opening a JSON file for preview before import. After import:

- the plant is registered in the workspace
- imported data and stats may become available for inspection
- referenced plugins are reconciled against the current workspace when possible

This is useful when:

- you received a plant JSON from another environment
- you want to inspect a file before registering it
- you want to restore a plant that is not currently loaded in the session

## Persisted Plant Shape

The real persisted payload can include more details, but a simplified plant shape looks like this:

```json
{
  "id": "plant_123",
  "name": "Oven 1",
  "sample_time_ms": 1000,
  "variables": [
    {
      "id": "var_0",
      "name": "Temperature",
      "type": "sensor",
      "unit": "C",
      "setpoint": 50.0,
      "pv_min": 0.0,
      "pv_max": 100.0
    },
    {
      "id": "var_1",
      "name": "Heater 1",
      "type": "atuador",
      "unit": "%",
      "setpoint": 0.0,
      "pv_min": 0.0,
      "pv_max": 100.0
    }
  ],
  "driver": {
    "plugin_id": "plugin_driver",
    "config": {
      "port": "/dev/ttyACM0"
    }
  },
  "controllers": []
}
```

## Connecting a Plant

Connecting a plant starts the runtime and live telemetry.

During connect, Senamby:

- validates the driver and active controllers
- resolves plugin files from the workspace
- prepares or reuses the Python environment
- sends the bootstrap to the Python runner

What you should expect after a successful connection:

- charts begin updating in real time
- runtime state becomes connected/running
- sensor setpoints can be pushed live
- controller edits may trigger hot update or `pending_restart`

## Disconnecting a Plant

Disconnecting:

- stops the live runtime
- keeps the plant open in the current session
- preserves the saved plant file

Use this when you want to stop execution without unloading the plant UI state.

## Pause and Resume

Pause and resume are visual session actions. The runtime keeps collecting and controlling in the background while the UI accumulates backlog. On resume, the queued telemetry is plotted.

Use pause when:

- you want to inspect a frozen chart
- you do not want the graph to keep moving temporarily
- you still want the runtime to keep running in the background

## Closing a Plant

Closing a plant:

- stops the runtime if it is connected
- unloads the plant from the current session
- keeps the persisted plant file

Important reopen rule:

- when a closed plant is reopened, controller instances start inactive

## Removing a Plant

Removing a plant:

- stops the runtime if needed
- unloads the plant from the session
- deletes the saved plant registry from the workspace

## Setpoints

Setpoints are saved to the plant registry and, when the plant is connected, pushed to the running runtime.

In practice:

- sensors are the variables that normally own setpoints
- actuator setpoints are not the normal live control path
- changing a sensor setpoint updates both saved state and live runtime state when connected

## Exporting Plant Data

The plotter can export the current collected session as:

- CSV
- JSON

Use CSV when you want spreadsheets or scripts.

Use JSON when you want:

- structured archive of the session
- offline analysis in Senamby's `Analyzer`
- sensor, setpoint, and actuator relationships preserved
