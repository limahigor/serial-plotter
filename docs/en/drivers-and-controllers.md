# Drivers and Controllers

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](drivers-and-controllers.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](../pt-BR/drivers-and-controllers.md)

## Driver Plugins

Drivers connect Senamby to the actual device or simulator. A driver is expected to:

- read sensors
- optionally read actuator feedback
- write actuator outputs when controllers are active

Driver configuration comes from the plugin schema and is stored in the plant driver instance.

## Step-by-Step: Creating a Driver Plugin

1. Open the `Plugins` module
2. Choose the `Driver` category
3. Create or import a plugin
4. Define:
   - plugin name
   - Python entry class
   - source file, usually `main.py`
   - schema fields required to configure the driver instance
   - optional Python dependencies
5. Save the plugin
6. In the `Plotter` module, assign that plugin to a plant and fill its configuration

Typical driver responsibilities:

- open and close the external connection
- read sensor data
- optionally read actuator feedback
- convert raw device units into public plant units
- write actuator outputs when controllers are active

## Controller Plugins

Controllers compute actuator outputs from the current cycle snapshot. A controller instance stores:

- identity and display name
- input bindings
- output bindings
- parameter values
- runtime status

## Step-by-Step: Creating a Controller Plugin

1. Open the `Plugins` module
2. Choose the `Controller` category
3. Create or import a controller plugin
4. Define:

   - plugin name
   - Python entry class
   - source file
   - controller parameter schema

5. Save the plugin
6. In the `Plotter` module, add a controller instance to a plant
7. Bind:
   - sensor inputs the controller reads
   - actuator outputs the controller writes
8. Set initial parameter values and activation state

Typical controller responsibilities:

- read the current snapshot
- compare sensors and setpoints
- produce actuator outputs in the plant's public engineering units

## Live Controller Updates

While a plant is connected, controllers can be added or edited live.

- if the current Python environment can load the updated set, the runtime hot-swaps the active controller list
- if a new controller requires environment changes, it is saved as `pending_restart`

Examples that may still need reconnect:

- dependency changes
- plugin source changes that require environment rebuild
- plugin sets that are no longer compatible with the hot runtime state

## Runtime Status

Current controller runtime statuses:

- `synced`: active configuration is already applied to the runtime
- `pending_restart`: configuration is saved, but the current runtime must be reconnected before it can use it

## Removal and Activation Rules

- an active synced controller cannot be removed while it is running
- deactivate it first, save the change, then remove it
- if a controller is inactive, removal is more permissive

## Public Unit Rule

Controllers and plants should work in the plant's public engineering units. Device-specific raw conversions belong in the driver.

Example:

- plant actuator range: `0..100`
- Arduino duty cycle: `0..255`
- controller output: `0..100`
- driver write conversion: `0..100 -> 0..255`
- driver readback conversion: `0..255 -> 0..100`

## Runtime Context Summary

At runtime:

- drivers receive `context.config` and `context.plant`
- drivers also receive `context.logger`
- controllers receive `context.controller` and `context.plant`
- controllers also receive `context.logger`
- controllers do not receive internal backend/runtime objects
- controller parameters are exposed as objects with fields like `.type`, `.value`, and `.label`
