# Senamby

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](docs/en/index.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](docs/pt-BR/index.md)

Senamby is a desktop workspace for creating, running, and analyzing plants driven by reusable drivers and controllers. It combines a Svelte/Tauri desktop UI, a Rust backend, and a Python runtime for plant plugins.

## What Senamby Includes

- **Plotter Workspace** for creating plants, connecting runtimes, plotting live data, and exporting sessions
- **Plugins workspace** for creating, importing, editing, and deleting reusable drivers and controllers
- **Analyzer** for loading exported JSON datasets and reviewing sensor, setpoint, and actuator behavior offline
- **Console** for centralized frontend/backend/runtime logs and alert rules

## Main User Workflows

1. Create or import the driver and controller plugins you need
2. Create a plant and configure variables, driver settings, and optional controllers
3. Connect the plant to start the live runtime
4. Monitor charts, change setpoints, and update controller configuration
5. Export CSV or JSON data from the plotter
6. Open exported JSON files in the Analyzer for offline inspection

## Documentation

- English: [docs/en/index.md](docs/en/index.md)
- Português (Brasil): [docs/pt-BR/index.md](docs/pt-BR/index.md)

## Run From Source

If you are running Senamby from source:

1. Install frontend dependencies inside `apps/desktop`
2. Start the desktop shell with Tauri
3. Open the app and use the sidebar modules:
   - `Plugins` to manage drivers and controllers
   - `Plotter` to manage plants and live runtimes
   - `Analyzer` to inspect exported JSON sessions
   - `Console` to review logs and manage alert rules

The current frontend scripts live in `apps/desktop/package.json`, including `pnpm --dir apps/desktop tauri dev`.

Typical local commands:

- `pnpm --dir apps/desktop install`
- `pnpm --dir apps/desktop tauri dev`

## Documentation Guide

- Start with [Getting Started](docs/en/getting-started.md) for a step-by-step first run
- Read [Core Concepts](docs/en/core-concepts.md) to understand plants, plugins, runtime, and session state
- Use [Plants](docs/en/plants.md) for creation, import, runtime actions, and export flows
- Use [Drivers and Controllers](docs/en/drivers-and-controllers.md) for plugin roles, bindings, runtime status, and live updates
- Use [Plugin File Format](docs/en/plugin-file-format.md) for JSON structure and Python plugin contracts
- Use [Runtime Behavior](docs/en/runtime-behavior.md) for the live execution model
- Use [Troubleshooting](docs/en/troubleshooting.md) for common runtime, dependency, and plugin issues
