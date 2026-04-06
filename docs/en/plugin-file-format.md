# Plugin File Format

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](plugin-file-format.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](../pt-BR/plugin-file-format.md)

## What This Document Covers

Use this guide when you want to:

- create a plugin from scratch
- import a plugin from JSON
- understand the Python code contract used at runtime
- know what data the driver or controller receives

## Supported Runtime

The current official execution path is **Python**.

Important note:

- the JSON importer can parse `runtime: "rust-native"`
- the current supported creation and execution flow for end users is still Python

## Plugin JSON Shape

Senamby accepts plugin JSON files with this common shape:

```json
{
  "name": "My Driver",
  "kind": "driver",
  "runtime": "python",
  "entryClass": "MyDriver",
  "sourceFile": "main.py",
  "schema": [
    {
      "name": "port",
      "type": "string",
      "description": "Serial port"
    },
    {
      "name": "baudrate",
      "type": "int",
      "defaultValue": 115200,
      "description": "Serial baud rate"
    }
  ],
  "dependencies": [
    {
      "name": "pyserial",
      "version": ""
    }
  ],
  "description": "Serial driver for a test device",
  "version": "1.0.0",
  "author": "Your Name"
}
```

Accepted aliases on import:

- `kind` or `type`
- `entryClass` or `entry_class`
- `sourceFile` or `source_file`
- `defaultValue` or `default_value`

## Supported Kinds and Field Types

Supported plugin kinds:

- `driver`
- `controller`

Supported schema field types:

- `bool`
- `int`
- `float`
- `string`
- `list`

Schema fields can optionally define:

- `defaultValue`
- `description`

## Creating a Plugin Through the UI

Step by step:

1. Open the `Plugins` module
2. Choose `Driver` or `Controller`
3. Create a new plugin or import a JSON file
4. Fill:
   - name
   - runtime `python`
   - entry class
   - source file
   - schema fields
   - optional Python dependencies
5. Save the plugin
6. Attach it to a plant in the `Plotter` module

## Driver Python Contract

```python
from typing import Any, Dict

class MyDriver:
    def __init__(self, context: Any) -> None:
        self.context = context

    def connect(self) -> bool:
        return True

    def stop(self) -> bool:
        return True

    def read(self) -> Dict[str, Dict[str, float]]:
        return {
            "sensors": {"var_0": 0.0},
            "actuators": {"var_2": 0.0}
        }

    def write(self, outputs: Dict[str, float]) -> bool:
        return True
```

Driver runtime context exposes only:

- `context.config`
- `context.plant`
- `context.logger`

### How to think about driver `context`

- `context.config` contains the driver's current configuration values
- those keys come from the plugin `schema`
- example: `self.context.config.get("port")`
- `context.plant` contains the plant's public runtime shape already normalized by the runtime
- `context.logger` sends structured logs to the `Console` module

### `context.plant` Structure

Inside both drivers and controllers, `context.plant` exposes:

- `context.plant.id`
- `context.plant.name`
- `context.plant.variables`
- `context.plant.variables_by_id`
- `context.plant.sensors`
- `context.plant.actuators`
- `context.plant.setpoints`

Useful reads:

- sensor ids: `self.context.plant.sensors.ids`
- actuator ids: `self.context.plant.actuators.ids`
- current sensor setpoint: `self.context.plant.setpoints.get(sensor_id, 0.0)`
- variable metadata: `self.context.plant.variables_by_id[sensor_id].unit`

Each variable in `context.plant.variables` or `context.plant.variables_by_id[...]` exposes:

- `.id`
- `.name`
- `.type`
- `.unit`
- `.setpoint`
- `.pv_min`
- `.pv_max`
- `.linked_sensor_ids`

Each `context.plant.sensors` and `context.plant.actuators` group exposes:

- `.ids`
- `.count`
- `.variables`
- `.variables_by_id`

### How to use `context.logger`

You can emit structured logs like:

- `self.context.logger.debug("message", {"key": value})`
- `self.context.logger.info("message", {"key": value})`
- `self.context.logger.warning("message", {"key": value})`
- `self.context.logger.error("message", {"key": value})`

### `read()` payload rules

`read()` should return an object with two maps:

```json
{
  "sensors": {
    "sensor_1": 58.2
  },
  "actuators": {
    "actuator_1": 37.0
  }
}
```

Practical rules:

- keys must be plant variable ids
- values must be finite numeric values
- missing `sensors` or `actuators` are treated as `{}` by the runtime
- unknown keys are ignored

### `write(outputs)` payload rules

When controller output exists in the current cycle, the runtime calls:

```python
write(outputs)
```

`outputs` looks like:

```json
{
  "actuator_1": 42.0,
  "actuator_2": 15.5
}
```

These values are already in the plant's public engineering units.

## Controller Python Contract

```python
from typing import Any, Dict

class MyController:
    def __init__(self, context: Any) -> None:
        self.context = context

    def compute(self, snapshot: Dict[str, Any]) -> Dict[str, float]:
        kp = self.context.controller.params["kp"].value
        sensor_id = self.context.controller.input_variable_ids[0]
        actuator_id = self.context.controller.output_variable_ids[0]
        pv = snapshot["sensors"].get(sensor_id, 0.0)
        sp = snapshot["setpoints"].get(sensor_id, 0.0)
        error = sp - pv
        return {actuator_id: kp * error}
```

Controller runtime context exposes only:

- `context.controller`
- `context.plant`
- `context.logger`

### Mental model: `context` vs `snapshot`

Use this simple rule:

- `context` = stable public plugin data for the current runtime state
- `snapshot` = serialized picture of the current cycle

In practice:

- read parameters normally from `self.context.controller.params["kp"].value`
- read dynamic signals from `snapshot["sensors"]`, `snapshot["setpoints"]`, and `snapshot["actuators"]`
- use `snapshot["controller"]` when you need the controller's serialized shape inside the cycle

Important distinction:

- `self.context.controller` is an object with attributes
- `snapshot["controller"]` is a serialized dictionary

That means:

- use `self.context.controller.params["kp"].value`
- do not assume `self.context["controller"]`
- do not assume `self.context.controller.params["kp"]["value"]`

## `context.controller` Structure

Inside a controller, `self.context.controller` exposes:

- `id`
- `name`
- `controller_type`
- `input_variable_ids`
- `output_variable_ids`
- `params`

Each entry in `params` exposes:

- `.key`
- `.type`
- `.value`
- `.label`

Direct examples:

- proportional gain: `self.context.controller.params["kp"].value`
- parameter label: `self.context.controller.params["kp"].label`
- parameter type: `self.context.controller.params["kp"].type`

## `compute(snapshot)` Basics

The controller snapshot includes:

- `cycle_id`
- `timestamp`
- `dt_s`
- `plant`
- `setpoints`
- `sensors`
- `actuators`
- `variables_by_id`
- `controller`

### Does `snapshot` include controller parameter values?

Yes.

The snapshot includes a serialized copy of the current controller at:

- `snapshot["controller"]`

And that also includes:

- `snapshot["controller"]["params"]`

Examples:

- `snapshot["controller"]["params"]["kp"]["value"]`
- `snapshot["controller"]["params"]["kp"]["label"]`
- `snapshot["controller"]["params"]["kp"]["type"]`

Practical difference:

- `self.context.controller.params["kp"].value` uses an object with attributes
- `snapshot["controller"]["params"]["kp"]["value"]` uses a serialized dictionary

When writing controller code, prefer:

- parameters and bindings: `self.context.controller`
- live cycle signals: `snapshot`

### Useful `snapshot` Structure

Most commonly used fields:

- `snapshot["cycle_id"]`
- `snapshot["timestamp"]`
- `snapshot["dt_s"]`
- `snapshot["plant"]["id"]`
- `snapshot["plant"]["name"]`
- `snapshot["setpoints"]`
- `snapshot["sensors"]`
- `snapshot["actuators"]`
- `snapshot["variables_by_id"]`
- `snapshot["controller"]`

Typical reads:

- current PV: `snapshot["sensors"].get(sensor_id, 0.0)`
- current SP: `snapshot["setpoints"].get(sensor_id, 0.0)`
- actuator readback: `snapshot["actuators"].get(actuator_id, 0.0)`
- variable unit: `snapshot["variables_by_id"][sensor_id]["unit"]`
- variable public setpoint: `snapshot["variables_by_id"][sensor_id]["setpoint"]`

Complete example:

```python
def compute(self, snapshot: Dict[str, Any]) -> Dict[str, float]:
    sensor_id = self.context.controller.input_variable_ids[0]
    actuator_id = self.context.controller.output_variable_ids[0]

    kp = self.context.controller.params["kp"].value
    pv = snapshot["sensors"].get(sensor_id, 0.0)
    sp = snapshot["setpoints"].get(sensor_id, 0.0)
    dt_s = snapshot["dt_s"]
    unit = snapshot["variables_by_id"][sensor_id]["unit"]

    self.context.logger.debug(
        "Computing controller",
        {"sensor_id": sensor_id, "pv": pv, "sp": sp, "dt_s": dt_s, "unit": unit},
    )

    error = sp - pv
    return {actuator_id: kp * error}
```

## Controller Return Payload

`compute()` must return a map `{actuator_id: value}`:

```json
{
  "actuator_1": 42.0
}
```

Practical rules:

- use actuator ids present in `output_variable_ids`
- values must be finite numeric values
- invalid output ids are ignored
- invalid numeric types can invalidate that controller cycle

## Public Units vs Device Units

Plant variables define public units and limits. Drivers are the correct place for raw-device conversion.

Example:

- public actuator range: `0..100`
- device duty cycle: `0..255`
- `write()` converts public output to raw device output
- `read()` converts raw device feedback back to public units

## Logging and Native Libraries

The runtime reserves `stdout` for the internal JSON protocol.

Guidance for plugin authors:

- use Python logging or `stderr` for logs
- avoid printing arbitrary text to `stdout`
- if you call native libraries, prefer libraries that log to `stderr`

The current runner redirects common native `stdout` output to `stderr`, but explicit `stderr` logging is still the safest path for plugin diagnostics.
