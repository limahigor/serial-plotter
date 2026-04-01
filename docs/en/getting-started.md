# Getting Started

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](getting-started.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](../pt-BR/getting-started.md)

## 1. Launch the App

If you run Senamby from source, the desktop app lives in `apps/desktop`.

Typical commands:

- `pnpm --dir apps/desktop install`
- `pnpm --dir apps/desktop tauri dev`

If you run a packaged build, start Senamby normally from your operating system.

## 2. Learn the Three Main Modules

When the app opens, the sidebar gives you three main areas:

- **Plotter**: live plants, runtime actions, charts, exports, and controller editing
- **Analyzer**: offline review of exported plant JSON files
- **Plugins**: reusable driver and controller definitions

If this is your first time, start in `Plugins`, then go to `Plotter`, and use `Analyzer` after exporting data.

## 3. Understand the Workspace

Senamby stores its working files under:

`Documents/Senamby/workspace`

Important folders:

- `drivers/`: persisted driver plugins
- `controllers/`: persisted controller plugins
- `plants/`: saved plant registries
- `envs/`: reusable Python environments
- `runtimes/`: bootstrap files and shared runner assets for connected sessions

You usually do not edit these files manually. The UI and backend manage them for you.

## 4. Create or Import a Driver Plugin

Before a plant can run, it needs a driver plugin.

Step by step:

1. Open the `Plugins` module
2. Select the `Driver` category
3. Choose one of these paths:
   - create a new plugin in the UI
   - import a plugin JSON file
   - reuse an existing plugin already loaded from the workspace
4. Confirm the plugin has:
   - a name
   - runtime `python`
   - an entry class
   - a source file, usually `main.py`
   - schema fields for the configuration the plant instance must provide
5. Save the plugin and verify it appears in the catalog

## 5. Optionally Create Controller Plugins

Controllers are optional. Add them when your plant should compute actuator outputs from live input data.

Step by step:

1. Stay in `Plugins`
2. Switch to the `Controller` category
3. Create or import one or more controller plugins
4. Make sure each controller exposes the right parameters and output bindings for your plant
5. Save and confirm the controllers appear in the catalog

## 6. Create or Import a Plant

Go to the `Plotter` module.

You can either:

- create a new plant from the UI
- import a plant JSON file with preview before registration

When creating a plant, fill these parts carefully:

1. **Plant identity**
   - name
   - sample time in milliseconds
2. **Variables**
   - sensor variables for measured process values
   - actuator variables for manipulated outputs
3. **Driver**
   - choose the driver plugin
   - fill the driver instance configuration required by the plugin schema
4. **Controllers** (optional)
   - add controller instances
   - bind sensor inputs and actuator outputs
   - adjust parameters and activation state

## 7. Connect the Plant

Once the plant is configured:

1. open it in the `Plotter` module
2. click connect
3. wait for the runtime to:
   - resolve the driver and active controllers
   - prepare or reuse the Python environment
   - start the live `read -> control -> write -> publish` cycle
4. confirm live telemetry starts appearing in the charts

If the plant cannot connect, go to [Troubleshooting](troubleshooting.md).

## 8. Work With a Live Session

While a plant is connected, you can:

- watch sensor and actuator plots in real time
- adjust sensor setpoints
- edit controller parameters
- save controller changes and let Senamby hot-update them when possible
- pause plotting temporarily without stopping the runtime

Important detail:

- `Pause` only pauses charting in the UI
- the runtime keeps running in the background
- when you resume, the queued telemetry is replayed into the charts

## 9. Export and Analyze Data

From the live plotter session, you can export:

- CSV for tabular processing
- JSON for structured replay and Analyzer usage

Recommended flow:

1. run the plant long enough to capture useful data
2. export JSON from the plotter toolbar
3. open the `Analyzer` module
4. load the exported JSON file
5. inspect sensors, setpoints, and linked actuators offline

## 10. Disconnect, Close, or Remove

These actions are different:

- **Disconnect**: stops the live runtime but keeps the plant open in the current session
- **Close plant**: unloads the plant from the session and stops the runtime if needed, but keeps the saved plant file
- **Remove plant**: unloads the plant and deletes the saved registry from the workspace

Important reopen rule:

- plants are not auto-loaded on startup
- a closed plant must be opened/imported again
- when reopened, controller instances start inactive
