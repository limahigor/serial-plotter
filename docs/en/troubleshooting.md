# Troubleshooting

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](troubleshooting.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](../pt-BR/troubleshooting.md)

## Plugin Not Found

Symptoms:

- connect fails
- a plant opens but cannot run
- imported plant references a plugin that is not available

What to check:

- the plugin exists in the workspace
- the plugin `id` or name still matches the plant
- the plugin source file and registry were not deleted manually
- the plugin catalog was reloaded successfully

## Controller Contract Errors

Common symptoms:

- controller validation fails
- connect fails with Python errors
- controller update fails after save

Common causes:

- using `context["controller"]` instead of `context.controller`
- using `self.context.controller.params["kp"]["value"]` instead of `.value`
- returning actuator ids that are not bound to that controller
- forgetting that `snapshot["controller"]` is a dict while `self.context.controller` is an object

## Controller `pending_restart`

Meaning:

- the controller was saved
- the current runtime environment cannot apply it immediately

Fix:

1. save the controller
2. disconnect the plant
3. reconnect the plant

## Cannot Remove Active Controller

If a controller is active and synced in a running plant, removal is blocked.

Fix:

1. deactivate the controller
2. save the plant/controller configuration
3. remove the controller

## Python Dependency Problems

If a runtime cannot start because of Python dependencies:

- verify the driver/controller dependency list
- reconnect the plant after fixing the plugin definition
- inspect the generated environment under `Documents/Senamby/workspace/envs/`

## "Invalid Message Received From Driver"

Typical symptom:

- the runtime reports that the driver sent invalid protocol data

What it means:

- the backend expected JSON lines on the runner protocol channel
- some text reached the protocol path unexpectedly

Current behavior:

- Python `print()` is redirected away from protocol `stdout`
- common native library `stdout` output is also redirected to `stderr`

If you still hit this problem:

- prefer logging to `stderr`
- avoid manual writes to `stdout`
- inspect native libraries that may bypass standard process handles entirely

## No Useful Data to Export or Analyze

If CSV/JSON export or Analyzer results look empty:

- make sure the plant was connected long enough to collect samples
- confirm live telemetry was actually arriving in the plotter
- for Analyzer, load the JSON exported by Senamby, not an arbitrary JSON file

## Closed vs Deleted Plant

If a plant disappears from the session:

- it may only have been closed, not deleted
- closed plants remain saved and can be opened/imported again
- deleted plants remove the persisted registry from the workspace
