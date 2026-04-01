# Senamby Documentation

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](index.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](../pt-BR/index.md)

## Overview

Senamby is a desktop application for operating plants through reusable plugins. A plant combines:

- sensors
- actuators
- one driver plugin
- zero or more controller plugins

The application lets you define plant models, connect them to a live runtime, monitor charts in real time, export runtime datasets, and analyze exported JSON files offline.

## Who This Is For

- operators configuring plants and running experiments
- integrators building driver plugins for devices and protocols
- control engineers creating controller plugins and bindings

## Main Modules in the App

- **Plotter**: create plants, connect runtimes, inspect live telemetry, export CSV/JSON, and manage controller state
- **Analyzer**: load exported plant JSON files and inspect sensors, setpoints, and linked actuators offline
- **Plugins**: create, import, edit, inspect, and delete reusable driver/controller plugins

## Documentation Map

- [Getting Started](getting-started.md)
- [Core Concepts](core-concepts.md)
- [Plants](plants.md)
- [Drivers and Controllers](drivers-and-controllers.md)
- [Plugin File Format](plugin-file-format.md)
- [Runtime Behavior](runtime-behavior.md)
- [Troubleshooting](troubleshooting.md)

## Recommended Reading Order

1. [Getting Started](getting-started.md)
2. [Core Concepts](core-concepts.md)
3. [Plants](plants.md)
4. [Drivers and Controllers](drivers-and-controllers.md)
5. [Plugin File Format](plugin-file-format.md)
6. [Runtime Behavior](runtime-behavior.md)
7. [Troubleshooting](troubleshooting.md)

## Common Step-by-Step Flow

1. Open the `Plugins` module and create or import a driver
2. Optionally create or import one or more controllers
3. Open the `Plotter` module and create a plant
4. Add variables, assign the driver, and configure plugin settings
5. Add controllers, bind sensor inputs and actuator outputs, then save
6. Connect the plant and wait for live telemetry
7. Adjust setpoints, pause/resume plotting when needed, and export data
8. Open the `Analyzer` module to inspect exported JSON sessions

## Language

- English: [index.md](index.md)
- Português (Brasil): [../pt-BR/index.md](../pt-BR/index.md)
