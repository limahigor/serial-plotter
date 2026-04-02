#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import inspect
import json
import os
import queue
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, TypeAlias, cast

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | List["JSONValue"] | Dict[str, "JSONValue"]
JsonObject: TypeAlias = Dict[str, Any]
SensorPayload: TypeAlias = Dict[str, float]
ActuatorPayload: TypeAlias = Dict[str, float]
ControllerOutputPayload: TypeAlias = Dict[str, float]

PROTOCOL_STDOUT: Optional[int] = None
PROTOCOL_STDOUT_LOCK = threading.Lock()
DRIVER_REQUIRED_METHODS = ("connect", "stop", "read")
DRIVER_WRITE_METHOD = "write"
CONTROLLER_REQUIRED_METHODS = ("compute",)


@dataclass
class VariableSpec:
    id: str
    name: str
    type: str
    unit: str
    setpoint: float
    pv_min: float
    pv_max: float
    linked_sensor_ids: List[str]


@dataclass
class IOGroup:
    ids: List[str]
    count: int
    variables: List[VariableSpec]
    variables_by_id: Dict[str, VariableSpec]


@dataclass
class PlantContext:
    id: str
    name: str
    variables: List[VariableSpec]
    variables_by_id: Dict[str, VariableSpec]
    sensors: IOGroup
    actuators: IOGroup
    setpoints: Dict[str, float]

    def apply_setpoints(self, next_setpoints: Dict[str, float]) -> None:
        self.setpoints = dict(next_setpoints)
        for variable_id, variable in self.variables_by_id.items():
            if variable_id in self.setpoints:
                variable.setpoint = self.setpoints[variable_id]
        for variable in self.variables:
            if variable.id in self.setpoints:
                variable.setpoint = self.setpoints[variable.id]


@dataclass(frozen=True)
class RuntimeTiming:
    owner: str
    clock: str
    strategy: str
    sample_time_ms: int


@dataclass(frozen=True)
class RuntimeSupervision:
    owner: str
    startup_timeout_ms: int
    shutdown_timeout_ms: int


@dataclass(frozen=True)
class RuntimePaths:
    runtime_dir: str
    venv_python_path: str
    runner_path: str
    bootstrap_path: str


@dataclass(frozen=True)
class RuntimeContext:
    id: str
    timing: RuntimeTiming
    supervision: RuntimeSupervision
    paths: RuntimePaths


@dataclass(frozen=True)
class DriverMetadata:
    plugin_id: str
    plugin_name: str
    plugin_dir: str
    source_file: str
    class_name: str
    config: Dict[str, JSONValue]


@dataclass
class ControllerParamSpec:
    key: str
    type: str
    value: JSONValue
    label: str


@dataclass
class ControllerMetadata:
    id: str
    plugin_id: str
    plugin_name: str
    plugin_dir: str
    source_file: str
    class_name: str
    name: str
    controller_type: str
    active: bool
    input_variable_ids: List[str]
    output_variable_ids: List[str]
    params: Dict[str, ControllerParamSpec]


@dataclass(frozen=True)
class ControllerPublicMetadata:
    id: str
    name: str
    controller_type: str
    input_variable_ids: List[str]
    output_variable_ids: List[str]
    params: Dict[str, ControllerParamSpec]

    def serialize(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "controller_type": self.controller_type,
            "input_variable_ids": list(self.input_variable_ids),
            "output_variable_ids": list(self.output_variable_ids),
            "params": serialize_controller_params(self.params),
        }


@dataclass(frozen=True)
class DriverPluginContext:
    config: Dict[str, JSONValue]
    plant: PlantContext
    logger: "RuntimePluginLogger"


@dataclass(frozen=True)
class ControllerPluginContext:
    controller: ControllerPublicMetadata
    plant: PlantContext
    logger: "RuntimePluginLogger"


@dataclass(frozen=True)
class RuntimeBootstrap:
    driver: DriverMetadata
    controllers: List[ControllerMetadata]
    plant: PlantContext
    runtime: RuntimeContext


@dataclass(frozen=True)
class CycleDurations:
    read_duration_ms: float = 0.0
    control_duration_ms: float = 0.0
    write_duration_ms: float = 0.0
    publish_duration_ms: float = 0.0
    controller_durations_ms: Dict[str, float] = field(default_factory=dict)


class DriverProtocol(Protocol):
    def connect(self) -> bool: ...

    def stop(self) -> bool: ...

    def read(self) -> Dict[str, Dict[str, float]]: ...

    def write(self, outputs: Dict[str, float]) -> bool | None: ...


class ControllerProtocol(Protocol):
    def compute(self, snapshot: Dict[str, Any]) -> Dict[str, float]: ...


@dataclass
class LoadedController:
    metadata: ControllerMetadata
    public_metadata: Dict[str, Any]
    instance: ControllerProtocol


@dataclass
class ControllerReloadResult:
    version: int
    controllers: List[ControllerMetadata]
    next_loaded: Optional[List[LoadedController]] = None
    fresh_loaded: List[LoadedController] = field(default_factory=list)
    stale_loaded: List[LoadedController] = field(default_factory=list)
    error: Optional[str] = None


class RuntimePluginLogger:
    def __init__(
        self,
        *,
        source_kind: str,
        runtime_id: str,
        plant_id: str,
        plugin_id: str,
        plugin_name: str,
        controller_id: Optional[str] = None,
        controller_name: Optional[str] = None,
    ) -> None:
        self.source_kind = source_kind
        self.runtime_id = runtime_id
        self.plant_id = plant_id
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name
        self.controller_id = controller_id
        self.controller_name = controller_name

    def debug(self, message: Any, details: Any = None) -> None:
        self._emit("debug", message, details)

    def info(self, message: Any, details: Any = None) -> None:
        self._emit("info", message, details)

    def warning(self, message: Any, details: Any = None) -> None:
        self._emit("warning", message, details)

    def error(self, message: Any, details: Any = None) -> None:
        self._emit("error", message, details)

    def _emit(self, level: str, message: Any, details: Any = None) -> None:
        payload: Dict[str, Any] = {
            "level": level,
            "message": str(message),
            "source_kind": self.source_kind,
            "plugin_id": self.plugin_id,
            "plugin_name": self.plugin_name,
        }
        if self.controller_id is not None:
            payload["controller_id"] = self.controller_id
        if self.controller_name is not None:
            payload["controller_name"] = self.controller_name
        normalized_details = normalize_log_details(details)
        if normalized_details is not None:
            payload["details"] = normalized_details
        emit("log", payload)


class PlantRuntimeEngine:
    def __init__(self, bootstrap: RuntimeBootstrap) -> None:
        self.bootstrap = bootstrap
        self.runtime_id = bootstrap.runtime.id
        self.plant_id = bootstrap.plant.id
        self.sample_time_ms = bootstrap.runtime.timing.sample_time_ms
        self.driver_instance: Optional[DriverProtocol] = None
        self.controllers: List[LoadedController] = []
        self.running = False
        self.paused = False
        self.should_exit = False
        self.cycle_id = 0
        self.runtime_started_at: Optional[float] = None
        self.first_cycle_started_at: Optional[float] = None
        self.last_cycle_started_at: Optional[float] = None
        self.next_cycle_deadline: Optional[float] = None
        self.paused_started_at: Optional[float] = None
        self.paused_duration_s = 0.0
        self.controller_reload_version = 0
        self.controller_reload_results: "queue.Queue[ControllerReloadResult]" = queue.Queue()

    def apply_init(self, bootstrap: RuntimeBootstrap) -> None:
        self._clear_pending_controller_reload_results()
        self.bootstrap = bootstrap
        self.runtime_id = bootstrap.runtime.id
        self.plant_id = bootstrap.plant.id
        self.sample_time_ms = bootstrap.runtime.timing.sample_time_ms
        self.driver_instance = None
        self.controllers = []
        self.running = False
        self.paused = False
        self.should_exit = False
        self.cycle_id = 0
        self.runtime_started_at = None
        self.first_cycle_started_at = None
        self.last_cycle_started_at = None
        self.next_cycle_deadline = None
        self.paused_started_at = None
        self.paused_duration_s = 0.0
        self.controller_reload_version = 0

    def start(self) -> None:
        if self.driver_instance is None:
            driver_cls = load_plugin_class(
                Path(self.bootstrap.driver.plugin_dir),
                self.bootstrap.driver.source_file,
                self.bootstrap.driver.class_name,
                DRIVER_REQUIRED_METHODS,
                "driver",
            )
            driver_context = build_driver_plugin_context(self.bootstrap)
            self.driver_instance = instantiate_plugin(
                driver_cls,
                driver_context,
                "driver",
            )
            attach_missing_attribute(self.driver_instance, "context", driver_context)
            attach_missing_attribute(self.driver_instance, "plant", driver_context.plant)
            attach_missing_attribute(self.driver_instance, "logger", driver_context.logger)

            if self.bootstrap.controllers and not callable(
                getattr(self.driver_instance, DRIVER_WRITE_METHOD, None)
            ):
                raise RuntimeError(
                    "Driver precisa implementar write(outputs) quando houver controladores ativos"
                )

            try:
                connected_result = self.driver_instance.connect()
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"Falha ao conectar driver '{self.bootstrap.driver.plugin_name}': {format_exception_message(exc)}"
                ) from exc

            connected = coerce_required_bool("connect", connected_result)
            if not connected:
                raise RuntimeError("Driver retornou False em connect()")

            self._replace_controllers(self.bootstrap.controllers)

        self.running = True
        self.paused = False
        now = time.monotonic()
        if self.runtime_started_at is None:
            self.runtime_started_at = now
        self.first_cycle_started_at = None
        self.next_cycle_deadline = now
        self.last_cycle_started_at = None

    def _stop_loaded_controllers(self, controllers: List[LoadedController]) -> None:
        for controller in controllers:
            maybe_call_optional_stop(controller.instance, controller.metadata.name)

    def _clear_pending_controller_reload_results(self) -> None:
        while True:
            try:
                result = self.controller_reload_results.get_nowait()
            except queue.Empty:
                break

            if result.fresh_loaded:
                self._stop_loaded_controllers(result.fresh_loaded)

    def _ensure_driver_write_support(
        self,
        controllers: List[ControllerMetadata],
    ) -> None:
        if controllers and self.driver_instance is not None and not callable(
            getattr(self.driver_instance, DRIVER_WRITE_METHOD, None)
        ):
            raise RuntimeError(
                "Driver precisa implementar write(outputs) quando houver controladores ativos"
            )

    def _load_controller(self, controller_meta: ControllerMetadata) -> LoadedController:
        controller_cls = load_plugin_class(
            Path(controller_meta.plugin_dir),
            controller_meta.source_file,
            controller_meta.class_name,
            CONTROLLER_REQUIRED_METHODS,
            f"controlador '{controller_meta.name}'",
        )
        context = build_controller_plugin_context(
            controller_meta,
            self.bootstrap.plant,
            self.bootstrap.runtime.id,
        )
        instance = instantiate_plugin(
            controller_cls,
            context,
            f"controlador '{controller_meta.name}'",
        )
        enrich_legacy_controller_aliases(instance, context)
        loaded = LoadedController(
            metadata=controller_meta,
            public_metadata=build_public_controller_metadata(controller_meta).serialize(),
            instance=cast(ControllerProtocol, instance),
        )
        maybe_call_optional_connect(loaded.instance, controller_meta.name)
        return loaded

    def _load_controllers(
        self,
        controllers: List[ControllerMetadata],
    ) -> List[LoadedController]:
        return [self._load_controller(controller_meta) for controller_meta in controllers]

    def _controller_metadata_fingerprint(self, metadata: ControllerMetadata) -> str:
        serialized = {
            "id": metadata.id,
            "plugin_id": metadata.plugin_id,
            "plugin_name": metadata.plugin_name,
            "plugin_dir": metadata.plugin_dir,
            "source_file": metadata.source_file,
            "class_name": metadata.class_name,
            "name": metadata.name,
            "controller_type": metadata.controller_type,
            "active": metadata.active,
            "input_variable_ids": list(metadata.input_variable_ids),
            "output_variable_ids": list(metadata.output_variable_ids),
            "params": serialize_controller_params(metadata.params),
        }
        return json.dumps(serialized, sort_keys=True, ensure_ascii=True)

    def _controller_runtime_reload_fingerprint(
        self,
        metadata: ControllerMetadata,
    ) -> str:
        serialized = {
            "id": metadata.id,
            "plugin_id": metadata.plugin_id,
            "plugin_name": metadata.plugin_name,
            "plugin_dir": metadata.plugin_dir,
            "source_file": metadata.source_file,
            "class_name": metadata.class_name,
            "active": metadata.active,
            "input_variable_ids": list(metadata.input_variable_ids),
            "output_variable_ids": list(metadata.output_variable_ids),
        }
        return json.dumps(serialized, sort_keys=True, ensure_ascii=True)

    def _can_preserve_loaded_controller(
        self,
        current: LoadedController,
        next_metadata: ControllerMetadata,
    ) -> bool:
        current_fingerprint = self._controller_metadata_fingerprint(current.metadata)
        next_fingerprint = self._controller_metadata_fingerprint(next_metadata)
        if current_fingerprint == next_fingerprint:
            return True

        return self._controller_runtime_reload_fingerprint(
            current.metadata
        ) == self._controller_runtime_reload_fingerprint(next_metadata)

    def _refresh_loaded_controller(
        self,
        current: LoadedController,
        next_metadata: ControllerMetadata,
    ) -> LoadedController:
        sync_loaded_controller_runtime_context(
            current.instance,
            build_controller_plugin_context(
                next_metadata,
                self.bootstrap.plant,
                self.bootstrap.runtime.id,
            ),
        )
        return LoadedController(
            metadata=next_metadata,
            public_metadata=build_public_controller_metadata(next_metadata).serialize(),
            instance=current.instance,
        )

    def _apply_loaded_controllers(
        self,
        controllers: List[ControllerMetadata],
        loaded: List[LoadedController],
    ) -> None:
        self.bootstrap = RuntimeBootstrap(
            driver=self.bootstrap.driver,
            controllers=list(controllers),
            plant=self.bootstrap.plant,
            runtime=self.bootstrap.runtime,
        )
        self.controllers = loaded

    def pause(self) -> None:
        if not self.paused:
            self.paused_started_at = time.monotonic()
        self.paused = True
        self.next_cycle_deadline = None
        self.last_cycle_started_at = None

    def resume(self) -> None:
        if self.paused_started_at is not None:
            paused_elapsed = max(0.0, time.monotonic() - self.paused_started_at)
            self.paused_duration_s += paused_elapsed
            if self.first_cycle_started_at is not None:
                self.first_cycle_started_at += paused_elapsed
            self.paused_started_at = None
        self.paused = False
        self.next_cycle_deadline = time.monotonic() + (self.sample_time_ms / 1000.0)
        self.last_cycle_started_at = None

    def update_setpoints(self, setpoints: Dict[str, float]) -> None:
        self.bootstrap.plant.apply_setpoints(setpoints)

    def update_controllers(self, controllers: List[ControllerMetadata]) -> None:
        if not self.running:
            self._replace_controllers(controllers)
            return

        self.controller_reload_version += 1
        version = self.controller_reload_version
        next_controllers = list(controllers)
        thread = threading.Thread(
            target=self._load_controllers_async,
            args=(version, next_controllers),
            daemon=True,
            name=f"controller-reload-{version}",
        )
        thread.start()

    def request_shutdown(self) -> None:
        self.should_exit = True
        self.running = False

    def next_wait_timeout(self) -> Optional[float]:
        if self.should_exit:
            return 0.0
        if not self.running or self.paused:
            return None
        if self.next_cycle_deadline is None:
            return 0.0
        return max(0.0, self.next_cycle_deadline - time.monotonic())

    def run_cycle(self) -> None:
        if not self.running or self.paused:
            return

        if self.next_cycle_deadline is None:
            self.next_cycle_deadline = time.monotonic()

        now = time.monotonic()
        if now < self.next_cycle_deadline:
            time.sleep(self.next_cycle_deadline - now)

        cycle_started_at = time.monotonic()
        self.cycle_id += 1
        if self.first_cycle_started_at is None:
            self.first_cycle_started_at = cycle_started_at
        effective_dt_ms = self._resolve_effective_dt_ms(cycle_started_at)

        sensors, actuators_read, durations, controller_outputs, written_outputs = self._execute_cycle(
            cycle_started_at,
            effective_dt_ms,
        )

        cycle_finished_at = time.monotonic()
        cycle_duration_ms = (cycle_finished_at - cycle_started_at) * 1000.0

        sample_step = self.sample_time_ms / 1000.0
        planned_next_deadline = (self.next_cycle_deadline or cycle_started_at) + sample_step
        late_by_ms = max(0.0, (cycle_finished_at - planned_next_deadline) * 1000.0)
        cycle_late = late_by_ms > 0.0

        publish_started_at = time.monotonic()
        telemetry_payload = {
            "timestamp": time.time(),
            "cycle_id": self.cycle_id,
            "configured_sample_time_ms": self.sample_time_ms,
            "effective_dt_ms": effective_dt_ms,
            "cycle_duration_ms": cycle_duration_ms,
            "read_duration_ms": durations.read_duration_ms,
            "control_duration_ms": durations.control_duration_ms,
            "write_duration_ms": durations.write_duration_ms,
            "publish_duration_ms": max(0.0, (time.monotonic() - publish_started_at) * 1000.0),
            "cycle_late": cycle_late,
            "late_by_ms": late_by_ms,
            "phase": "publish_telemetry",
            "uptime_s": self._resolve_uptime_s(cycle_started_at),
            "sensors": sensors,
            "actuators": written_outputs or actuators_read,
            "actuators_read": actuators_read,
            "setpoints": self.bootstrap.plant.setpoints,
            "controller_outputs": controller_outputs,
            "written_outputs": written_outputs,
            "controller_durations_ms": durations.controller_durations_ms,
        }
        emit("telemetry", telemetry_payload)

        if cycle_late:
            emit(
                "cycle_overrun",
                {
                    "cycle_id": self.cycle_id,
                    "configured_sample_time_ms": self.sample_time_ms,
                    "cycle_duration_ms": cycle_duration_ms,
                    "late_by_ms": late_by_ms,
                    "phase": "publish_telemetry",
                },
            )

        self.next_cycle_deadline = planned_next_deadline
        while self.next_cycle_deadline < time.monotonic():
            self.next_cycle_deadline += sample_step

        self.last_cycle_started_at = cycle_started_at

    def _execute_cycle(
        self,
        cycle_started_at: float,
        effective_dt_ms: float,
    ) -> tuple[SensorPayload, ActuatorPayload, CycleDurations, ControllerOutputPayload, ActuatorPayload]:
        sensors: SensorPayload = {}
        actuators_read: ActuatorPayload = {}
        controller_outputs: ControllerOutputPayload = {}
        written_outputs: ActuatorPayload = {}
        controller_durations: Dict[str, float] = {}

        read_started_at = time.monotonic()
        try:
            if self.driver_instance is not None:
                sensors, actuators_read = normalize_read_snapshot(
                    self.driver_instance.read(),
                    self.bootstrap.plant,
                )
        except Exception as exc:  # noqa: BLE001
            log_error(traceback.format_exc())
            emit(
                "warning",
                {
                    "message": f"Falha em leitura de driver: {exc}",
                    "source_kind": "driver",
                    "plugin_id": self.bootstrap.driver.plugin_id,
                    "plugin_name": self.bootstrap.driver.plugin_name,
                },
            )
        read_duration_ms = (time.monotonic() - read_started_at) * 1000.0

        control_started_at = time.monotonic()
        for controller in self.controllers:
            compute_started_at = time.monotonic()
            try:
                snapshot = build_controller_snapshot(
                    cycle_id=self.cycle_id,
                    cycle_started_at=cycle_started_at,
                    dt_ms=effective_dt_ms,
                    plant=self.bootstrap.plant,
                    controller_public_metadata=controller.public_metadata,
                    sensors=sensors,
                    actuators=actuators_read,
                )
                outputs = normalize_controller_outputs(
                    controller.instance.compute(snapshot),
                    controller.metadata.output_variable_ids,
                    controller.metadata.name,
                )
                for variable_id, value in outputs.items():
                    if variable_id in controller_outputs:
                        raise RuntimeError(
                            f"Saída '{variable_id}' recebeu mais de um valor no mesmo ciclo"
                        )
                    controller_outputs[variable_id] = value
            except Exception as exc:  # noqa: BLE001
                log_error(traceback.format_exc())
                emit(
                    "warning",
                    {
                        "message": f"Falha no controlador '{controller.metadata.name}': {exc}",
                        "source_kind": "controller",
                        "plugin_id": controller.metadata.plugin_id,
                        "plugin_name": controller.metadata.plugin_name,
                        "controller_id": controller.metadata.id,
                        "controller_name": controller.metadata.name,
                    },
                )
            finally:
                controller_durations[controller.metadata.id] = (
                    time.monotonic() - compute_started_at
                ) * 1000.0
        control_duration_ms = (time.monotonic() - control_started_at) * 1000.0

        write_started_at = time.monotonic()
        if controller_outputs and self.driver_instance is not None:
            try:
                write_status = self.driver_instance.write(dict(controller_outputs))
                coerce_optional_bool(
                    "write",
                    write_status,
                    "Driver retornou False em write(outputs)",
                )
                written_outputs = dict(controller_outputs)
            except Exception as exc:  # noqa: BLE001
                log_error(traceback.format_exc())
                emit(
                    "warning",
                    {
                        "message": f"Falha em escrita de driver: {exc}",
                        "source_kind": "driver",
                        "plugin_id": self.bootstrap.driver.plugin_id,
                        "plugin_name": self.bootstrap.driver.plugin_name,
                    },
                )
        write_duration_ms = (time.monotonic() - write_started_at) * 1000.0

        return (
            sensors,
            actuators_read,
            CycleDurations(
                read_duration_ms=read_duration_ms,
                control_duration_ms=control_duration_ms,
                write_duration_ms=write_duration_ms,
                controller_durations_ms=controller_durations,
            ),
            controller_outputs,
            written_outputs,
        )

    def _resolve_effective_dt_ms(self, cycle_started_at: float) -> float:
        if self.last_cycle_started_at is None:
            return float(self.sample_time_ms)
        return max(0.0, (cycle_started_at - self.last_cycle_started_at) * 1000.0)

    def _resolve_uptime_s(self, cycle_started_at: float) -> float:
        if self.cycle_id == 1:
            return 0.0
        first_cycle_started_at = self.first_cycle_started_at or cycle_started_at
        return max(0.0, cycle_started_at - first_cycle_started_at)

    def stop(self) -> None:
        self._clear_pending_controller_reload_results()
        for controller in self.controllers:
            maybe_call_optional_stop(controller.instance, controller.metadata.name)
        self.controllers = []
        if self.driver_instance is not None:
            try:
                stopped = coerce_required_bool("stop", self.driver_instance.stop())
                if not stopped:
                    emit(
                        "warning",
                        {
                            "message": "Driver retornou False em stop()",
                            "source_kind": "driver",
                            "plugin_id": self.bootstrap.driver.plugin_id,
                            "plugin_name": self.bootstrap.driver.plugin_name,
                        },
                    )
            except Exception as exc:  # noqa: BLE001
                log_error(f"Falha ao finalizar driver: {exc}")

    def apply_pending_controller_reload(self) -> None:
        while True:
            try:
                result = self.controller_reload_results.get_nowait()
            except queue.Empty:
                break

            if result.version != self.controller_reload_version:
                if result.fresh_loaded:
                    self._stop_loaded_controllers(result.fresh_loaded)
                continue

            if result.error is not None:
                emit("error", {"message": f"Falha ao atualizar controladores: {result.error}"})
                continue

            self._apply_loaded_controllers(result.controllers, result.next_loaded or [])
            self._stop_loaded_controllers(result.stale_loaded)

    def _replace_controllers(self, controllers: List[ControllerMetadata]) -> None:
        self._ensure_driver_write_support(controllers)
        loaded = self._load_controllers(controllers)
        stale_loaded = list(self.controllers)
        self._apply_loaded_controllers(controllers, loaded)
        self._stop_loaded_controllers(stale_loaded)

    def _load_controllers_async(
        self,
        version: int,
        controllers: List[ControllerMetadata],
    ) -> None:
        fresh_loaded: List[LoadedController] = []
        try:
            self._ensure_driver_write_support(controllers)
            current_controllers = list(self.controllers)
            current_by_id = {
                controller.metadata.id: controller for controller in current_controllers
            }
            preserved_by_id: Dict[str, LoadedController] = {}
            fresh_by_id: Dict[str, LoadedController] = {}

            for controller_meta in controllers:
                current = current_by_id.get(controller_meta.id)
                if current is not None and self._can_preserve_loaded_controller(
                    current,
                    controller_meta,
                ):
                    preserved_by_id[controller_meta.id] = self._refresh_loaded_controller(
                        current,
                        controller_meta,
                    )
                    continue

                loaded_controller = self._load_controller(controller_meta)
                fresh_loaded.append(loaded_controller)
                fresh_by_id[controller_meta.id] = loaded_controller

            next_loaded: List[LoadedController] = []
            for controller_meta in controllers:
                preserved = preserved_by_id.get(controller_meta.id)
                if preserved is not None:
                    next_loaded.append(preserved)
                    continue

                fresh = fresh_by_id.get(controller_meta.id)
                if fresh is None:
                    raise RuntimeError(
                        f"Falha ao preparar controlador '{controller_meta.name}' para hot-reload"
                    )
                next_loaded.append(fresh)

            stale_loaded = [
                controller
                for controller in current_controllers
                if controller.metadata.id not in preserved_by_id
            ]
            self.controller_reload_results.put(
                ControllerReloadResult(
                    version=version,
                    controllers=list(controllers),
                    next_loaded=next_loaded,
                    fresh_loaded=list(fresh_loaded),
                    stale_loaded=stale_loaded,
                )
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(exc)
            self._stop_loaded_controllers(fresh_loaded)
            self.controller_reload_results.put(
                ControllerReloadResult(
                    version=version,
                    controllers=list(controllers),
                    error=format_exception_message(exc),
                )
            )


def _require_stream_fd(stream: Any, name: str) -> int:
    if stream is None or not hasattr(stream, "fileno"):
        raise RuntimeError(f"{name} não expõe um descritor de arquivo")
    try:
        return int(stream.fileno())
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Falha ao obter descritor de arquivo de {name}: {exc}") from exc


def _sync_windows_stdout_handle_to_stderr() -> None:
    if os.name != "nt":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        invalid_handle = ctypes.c_void_p(-1).value
        stdout_handle_id = -11
        stderr_handle_id = -12

        stderr_handle = kernel32.GetStdHandle(stderr_handle_id)
        if stderr_handle in (0, invalid_handle):
            raise ctypes.WinError()

        if not kernel32.SetStdHandle(stdout_handle_id, stderr_handle):
            raise ctypes.WinError()
    except Exception as exc:  # noqa: BLE001
        log_error(f"Aviso: não foi possível sincronizar stdout do Windows com stderr: {exc}")


def bootstrap_protocol_stdout() -> None:
    global PROTOCOL_STDOUT

    if PROTOCOL_STDOUT is not None:
        return

    stdout_stream = sys.__stdout__
    stderr_stream = sys.__stderr__
    stdout_fd = _require_stream_fd(stdout_stream, "stdout")
    stderr_fd = _require_stream_fd(stderr_stream, "stderr")

    stdout_stream.flush()
    stderr_stream.flush()

    try:
        protocol_stdout_fd = os.dup(stdout_fd)
    except OSError as exc:
        raise RuntimeError(f"Falha ao duplicar stdout do protocolo: {exc}") from exc

    try:
        try:
            os.set_inheritable(protocol_stdout_fd, False)
        except OSError:
            pass

        PROTOCOL_STDOUT = protocol_stdout_fd
        os.dup2(stderr_fd, stdout_fd)
        sys.stdout = sys.stderr
        _sync_windows_stdout_handle_to_stderr()
    except Exception:  # noqa: BLE001
        PROTOCOL_STDOUT = None
        try:
            os.close(protocol_stdout_fd)
        except OSError:
            pass
        raise


def _resolve_protocol_stdout_fd() -> int:
    if PROTOCOL_STDOUT is not None:
        return PROTOCOL_STDOUT
    return _require_stream_fd(sys.__stdout__, "stdout")


def emit(msg_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
    envelope: Dict[str, Any] = {"type": msg_type}
    if payload is not None:
        envelope["payload"] = payload
    data = (
        json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    protocol_stdout_fd = _resolve_protocol_stdout_fd()
    total_written = 0

    with PROTOCOL_STDOUT_LOCK:
        while total_written < len(data):
            try:
                written = os.write(protocol_stdout_fd, data[total_written:])
            except InterruptedError:
                continue
            if written <= 0:
                raise RuntimeError("Falha ao escrever envelope no stdout do protocolo")
            total_written += written


def log_error(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def format_exception_message(exc: BaseException) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def log_exception(exc: BaseException) -> None:
    if isinstance(exc, RuntimeError):
        log_error(str(exc))
        return
    log_error(traceback.format_exc())


def normalize_log_details(value: Any) -> JSONValue | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return cast(JSONValue, value)
    if isinstance(value, list):
        return [
            cast(JSONValue, normalize_log_details(item))
            for item in value
        ]
    if isinstance(value, dict):
        normalized: Dict[str, JSONValue] = {}
        for key, item in value.items():
            normalized[str(key)] = cast(JSONValue, normalize_log_details(item))
        return cast(JSONValue, normalized)
    return cast(JSONValue, str(value))


def expect_dict(raw_value: Any, context: str) -> JsonObject:
    if not isinstance(raw_value, dict):
        raise RuntimeError(f"{context} deve ser um objeto JSON")
    return cast(JsonObject, raw_value)


def normalize_string(raw_value: Any, context: str) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise RuntimeError(f"{context} deve ser uma string não vazia")
    return raw_value.strip()


def normalize_non_negative_int(raw_value: Any, context: str, default: int = 0) -> int:
    if raw_value is None:
        return default
    resolved = int(raw_value)
    if resolved < 0:
        raise RuntimeError(f"{context} não pode ser negativo")
    return resolved


def normalize_positive_int(raw_value: Any, context: str, default: int = 1) -> int:
    resolved = normalize_non_negative_int(raw_value, context, default)
    if resolved <= 0:
        raise RuntimeError(f"{context} deve ser maior que zero")
    return resolved


def normalize_string_list(raw_value: Any, context: str) -> List[str]:
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise RuntimeError(f"{context} deve ser um array")
    return [str(value) for value in raw_value]


def normalize_json_map(raw_value: Any, context: str) -> Dict[str, JSONValue]:
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise RuntimeError(f"{context} deve ser um objeto JSON")
    return {str(key): cast(JSONValue, value) for key, value in raw_value.items()}


def normalize_float_map(
    raw_value: Any,
    context: str,
    allowed_keys: Optional[set[str]] = None,
) -> Dict[str, float]:
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise RuntimeError(f"{context} deve ser um objeto JSON")

    normalized: Dict[str, float] = {}
    for key, value in raw_value.items():
        key_str = str(key)
        if allowed_keys is not None and key_str not in allowed_keys:
            continue
        try:
            numeric_value = float(value)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"{context}.{key_str} deve ser numérico") from exc
        if numeric_value != numeric_value or numeric_value in (float("inf"), float("-inf")):
            raise RuntimeError(f"{context}.{key_str} deve ser finito")
        normalized[key_str] = numeric_value
    return normalized


def normalize_variable(raw_value: Any, context: str) -> VariableSpec:
    raw = expect_dict(raw_value, context)
    linked_sensor_ids_raw = raw.get("linked_sensor_ids")
    linked_sensor_ids = (
        normalize_string_list(linked_sensor_ids_raw, f"{context}.linked_sensor_ids")
        if linked_sensor_ids_raw is not None
        else []
    )
    return VariableSpec(
        id=normalize_string(raw.get("id"), f"{context}.id"),
        name=normalize_string(raw.get("name"), f"{context}.name"),
        type=normalize_string(raw.get("type"), f"{context}.type"),
        unit=normalize_string(raw.get("unit"), f"{context}.unit"),
        setpoint=float(raw.get("setpoint", 0.0) or 0.0),
        pv_min=float(raw.get("pv_min", 0.0) or 0.0),
        pv_max=float(raw.get("pv_max", 0.0) or 0.0),
        linked_sensor_ids=linked_sensor_ids,
    )


def normalize_variable_list(raw_value: Any, context: str) -> List[VariableSpec]:
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise RuntimeError(f"{context} deve ser um array")
    return [
        normalize_variable(item, f"{context}[{index}]")
        for index, item in enumerate(raw_value)
    ]


def normalize_variable_map(raw_value: Any, context: str) -> Dict[str, VariableSpec]:
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise RuntimeError(f"{context} deve ser um objeto JSON")

    normalized: Dict[str, VariableSpec] = {}
    for key, value in raw_value.items():
        variable = normalize_variable(value, f"{context}.{key}")
        normalized[variable.id] = variable
    return normalized


def build_variable_map(variables: List[VariableSpec]) -> Dict[str, VariableSpec]:
    return {variable.id: variable for variable in variables}


def normalize_io_group(raw_value: Any, context: str) -> IOGroup:
    raw = expect_dict(raw_value, context)
    variables = normalize_variable_list(raw.get("variables"), f"{context}.variables")
    variables_by_id = normalize_variable_map(raw.get("variables_by_id"), f"{context}.variables_by_id")
    if not variables_by_id:
        variables_by_id = build_variable_map(variables)
    if not variables:
        variables = list(variables_by_id.values())

    ids = normalize_string_list(raw.get("ids"), f"{context}.ids")
    if not ids:
        ids = [variable.id for variable in variables]

    count = normalize_non_negative_int(raw.get("count"), f"{context}.count", len(ids))
    return IOGroup(ids=ids, count=count, variables=variables, variables_by_id=variables_by_id)


def normalize_plant_context(raw_value: Any) -> PlantContext:
    raw = expect_dict(raw_value, "bootstrap.plant")
    variables = normalize_variable_list(raw.get("variables"), "bootstrap.plant.variables")
    if not variables:
        raise RuntimeError("bootstrap.plant.variables deve conter pelo menos uma variável")
    variables_by_id = build_variable_map(variables)
    sensor_ids = normalize_string_list(raw.get("sensor_ids"), "bootstrap.plant.sensor_ids")
    actuator_ids = normalize_string_list(raw.get("actuator_ids"), "bootstrap.plant.actuator_ids")
    if not sensor_ids:
        sensor_ids = [variable.id for variable in variables if variable.type == "sensor"]
    if not actuator_ids:
        actuator_ids = [variable.id for variable in variables if variable.type == "atuador"]

    sensor_variables = [variables_by_id[variable_id] for variable_id in sensor_ids if variable_id in variables_by_id]
    actuator_variables = [
        variables_by_id[variable_id] for variable_id in actuator_ids if variable_id in variables_by_id
    ]

    return PlantContext(
        id=normalize_string(raw.get("id"), "bootstrap.plant.id"),
        name=normalize_string(raw.get("name"), "bootstrap.plant.name"),
        variables=variables,
        variables_by_id=variables_by_id,
        sensors=IOGroup(
            ids=sensor_ids,
            count=len(sensor_variables),
            variables=sensor_variables,
            variables_by_id=build_variable_map(sensor_variables),
        ),
        actuators=IOGroup(
            ids=actuator_ids,
            count=len(actuator_variables),
            variables=actuator_variables,
            variables_by_id=build_variable_map(actuator_variables),
        ),
        setpoints=normalize_float_map(raw.get("setpoints"), "bootstrap.plant.setpoints"),
    )


def normalize_runtime_context(raw_value: Any) -> RuntimeContext:
    raw = expect_dict(raw_value, "bootstrap.runtime")
    timing_raw = expect_dict(raw.get("timing"), "bootstrap.runtime.timing")
    supervision_raw = expect_dict(raw.get("supervision"), "bootstrap.runtime.supervision")
    paths_raw = expect_dict(raw.get("paths"), "bootstrap.runtime.paths")

    return RuntimeContext(
        id=normalize_string(raw.get("id"), "bootstrap.runtime.id"),
        timing=RuntimeTiming(
            owner=normalize_string(timing_raw.get("owner"), "bootstrap.runtime.timing.owner"),
            clock=normalize_string(timing_raw.get("clock"), "bootstrap.runtime.timing.clock"),
            strategy=normalize_string(timing_raw.get("strategy"), "bootstrap.runtime.timing.strategy"),
            sample_time_ms=normalize_positive_int(
                timing_raw.get("sample_time_ms"),
                "bootstrap.runtime.timing.sample_time_ms",
                100,
            ),
        ),
        supervision=RuntimeSupervision(
            owner=normalize_string(
                supervision_raw.get("owner"),
                "bootstrap.runtime.supervision.owner",
            ),
            startup_timeout_ms=normalize_positive_int(
                supervision_raw.get("startup_timeout_ms"),
                "bootstrap.runtime.supervision.startup_timeout_ms",
                1000,
            ),
            shutdown_timeout_ms=normalize_positive_int(
                supervision_raw.get("shutdown_timeout_ms"),
                "bootstrap.runtime.supervision.shutdown_timeout_ms",
                1000,
            ),
        ),
        paths=RuntimePaths(
            runtime_dir=normalize_string(
                paths_raw.get("runtime_dir"),
                "bootstrap.runtime.paths.runtime_dir",
            ),
            venv_python_path=normalize_string(
                paths_raw.get("venv_python_path"),
                "bootstrap.runtime.paths.venv_python_path",
            ),
            runner_path=normalize_string(
                paths_raw.get("runner_path"),
                "bootstrap.runtime.paths.runner_path",
            ),
            bootstrap_path=normalize_string(
                paths_raw.get("bootstrap_path"),
                "bootstrap.runtime.paths.bootstrap_path",
            ),
        ),
    )


def normalize_driver_metadata(raw_value: Any) -> DriverMetadata:
    raw = expect_dict(raw_value, "bootstrap.driver")
    return DriverMetadata(
        plugin_id=normalize_string(raw.get("plugin_id"), "bootstrap.driver.plugin_id"),
        plugin_name=normalize_string(raw.get("plugin_name"), "bootstrap.driver.plugin_name"),
        plugin_dir=normalize_string(raw.get("plugin_dir"), "bootstrap.driver.plugin_dir"),
        source_file=normalize_string(raw.get("source_file"), "bootstrap.driver.source_file"),
        class_name=normalize_string(raw.get("class_name"), "bootstrap.driver.class_name"),
        config=normalize_json_map(raw.get("config"), "bootstrap.driver.config"),
    )


def normalize_controller_param(raw_value: Any, context: str, key: str) -> ControllerParamSpec:
    raw = expect_dict(raw_value, context)
    return ControllerParamSpec(
        key=key,
        type=normalize_string(raw.get("type"), f"{context}.type"),
        value=cast(JSONValue, raw.get("value")),
        label=normalize_string(raw.get("label"), f"{context}.label"),
    )


def normalize_controller_metadata(raw_value: Any, index: int) -> ControllerMetadata:
    context = f"bootstrap.controllers[{index}]"
    raw = expect_dict(raw_value, context)
    params_raw = expect_dict(raw.get("params") or {}, f"{context}.params")

    return ControllerMetadata(
        id=normalize_string(raw.get("id"), f"{context}.id"),
        plugin_id=normalize_string(raw.get("plugin_id"), f"{context}.plugin_id"),
        plugin_name=normalize_string(raw.get("plugin_name"), f"{context}.plugin_name"),
        plugin_dir=normalize_string(raw.get("plugin_dir"), f"{context}.plugin_dir"),
        source_file=normalize_string(raw.get("source_file"), f"{context}.source_file"),
        class_name=normalize_string(raw.get("class_name"), f"{context}.class_name"),
        name=normalize_string(raw.get("name"), f"{context}.name"),
        controller_type=normalize_string(raw.get("controller_type"), f"{context}.controller_type"),
        active=bool(raw.get("active", True)),
        input_variable_ids=normalize_string_list(raw.get("input_variable_ids"), f"{context}.input_variable_ids"),
        output_variable_ids=normalize_string_list(raw.get("output_variable_ids"), f"{context}.output_variable_ids"),
        params={
            str(key): normalize_controller_param(value, f"{context}.params.{key}", str(key))
            for key, value in params_raw.items()
        },
    )


def normalize_bootstrap(raw_value: Any) -> RuntimeBootstrap:
    raw = expect_dict(raw_value, "bootstrap")
    controllers_raw = raw.get("controllers")
    if controllers_raw is None:
        controllers: List[ControllerMetadata] = []
    elif not isinstance(controllers_raw, list):
        raise RuntimeError("bootstrap.controllers deve ser um array")
    else:
        controllers = [
            normalize_controller_metadata(controller_raw, index)
            for index, controller_raw in enumerate(controllers_raw)
        ]

    return RuntimeBootstrap(
        driver=normalize_driver_metadata(raw.get("driver")),
        controllers=controllers,
        plant=normalize_plant_context(raw.get("plant")),
        runtime=normalize_runtime_context(raw.get("runtime")),
    )


def load_plugin_class(
    plugin_dir: Path,
    source_file: str,
    expected_class_name: str,
    required_methods: tuple[str, ...],
    component_label: str,
) -> type[Any]:
    source_path = plugin_dir / source_file
    if not source_path.exists():
        raise RuntimeError(f"{source_file} não encontrado em '{source_path}'")

    module_hash = hashlib.sha1(str(source_path.resolve()).encode("utf-8")).hexdigest()[:12]
    module_name = f"runtime_plugin_{expected_class_name.lower()}_{module_hash}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        str(source_path),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Falha ao criar spec do módulo do {component_label}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    candidate = getattr(module, expected_class_name, None)
    if candidate is None or not inspect.isclass(candidate):
        raise RuntimeError(
            f"Classe '{expected_class_name}' não encontrada em {source_file} para o {component_label}"
        )
    if candidate.__module__ != module.__name__:
        raise RuntimeError(
            f"Classe '{expected_class_name}' precisa ser definida em {source_file}"
        )

    missing = [
        method
        for method in required_methods
        if not callable(getattr(candidate, method, None))
    ]
    if missing:
        raise RuntimeError(
            f"Classe '{expected_class_name}' inválida para o {component_label}. Métodos ausentes: {', '.join(missing)}"
        )

    return candidate


def instantiate_plugin(plugin_cls: type[Any], context: Any, component_label: str) -> Any:
    try:
        return plugin_cls(context)
    except TypeError as exc:
        raise RuntimeError(
            f"Construtor do {component_label} deve seguir o contrato __init__(self, context)"
        ) from exc


def attach_missing_attribute(target: Any, attr_name: str, value: Any) -> None:
    try:
        current_value = getattr(target, attr_name)
    except AttributeError:
        current_value = None
    except Exception:  # noqa: BLE001
        return

    if current_value is not None:
        return

    try:
        setattr(target, attr_name, value)
    except Exception:  # noqa: BLE001
        return


def enrich_legacy_controller_aliases(
    instance: Any,
    context: ControllerPluginContext,
) -> None:
    attach_missing_attribute(instance, "context", context)
    attach_missing_attribute(instance, "plant", context.plant)
    attach_missing_attribute(instance, "logger", context.logger)

    try:
        controller_alias = getattr(instance, "controller")
    except AttributeError:
        controller_alias = None
    except Exception:  # noqa: BLE001
        return

    if controller_alias is None:
        attach_missing_attribute(instance, "controller", context.controller)
        return

    if controller_alias is context.controller:
        return

    # Some workspace controllers keep an internal `self.controller` object and
    # still expect runtime metadata such as output_variable_ids to be available there.
    for attr_name in (
        "id",
        "name",
        "controller_type",
        "input_variable_ids",
        "output_variable_ids",
        "params",
    ):
        attach_missing_attribute(
            controller_alias,
            attr_name,
            copy.deepcopy(getattr(context.controller, attr_name)),
        )


def overwrite_attribute(target: Any, attr_name: str, value: Any) -> None:
    try:
        setattr(target, attr_name, value)
    except Exception:  # noqa: BLE001
        return


def sync_controller_public_metadata(target: Any, metadata: ControllerPublicMetadata) -> None:
    for attr_name in (
        "id",
        "name",
        "controller_type",
        "input_variable_ids",
        "output_variable_ids",
        "params",
    ):
        overwrite_attribute(target, attr_name, copy.deepcopy(getattr(metadata, attr_name)))


def sync_loaded_controller_runtime_context(
    instance: Any,
    context: ControllerPluginContext,
) -> None:
    overwrite_attribute(instance, "context", context)
    overwrite_attribute(instance, "plant", context.plant)
    overwrite_attribute(instance, "logger", context.logger)

    try:
        controller_alias = getattr(instance, "controller")
    except AttributeError:
        controller_alias = None
    except Exception:  # noqa: BLE001
        return

    if controller_alias is None:
        overwrite_attribute(instance, "controller", copy.deepcopy(context.controller))
        return

    if controller_alias is context.controller:
        return

    sync_controller_public_metadata(controller_alias, context.controller)


def coerce_required_bool(method_name: str, result: Any) -> bool:
    if not isinstance(result, bool):
        raise RuntimeError(
            f"Método '{method_name}' deve retornar bool, recebeu {type(result).__name__}"
        )
    return result


def coerce_optional_bool(method_name: str, result: Any, false_message: str) -> None:
    if result is None:
        return
    if not isinstance(result, bool):
        raise RuntimeError(
            f"Método '{method_name}' deve retornar bool ou None, recebeu {type(result).__name__}"
        )
    if not result:
        emit("warning", {"message": false_message})


def maybe_call_optional_connect(instance: Any, component_name: str) -> None:
    connect = getattr(instance, "connect", None)
    if not callable(connect):
        return
    result = connect()
    coerce_optional_bool(
        "connect",
        result,
        f"Componente '{component_name}' retornou False em connect()",
    )


def maybe_call_optional_stop(instance: Any, component_name: str) -> None:
    stop = getattr(instance, "stop", None)
    if not callable(stop):
        return
    try:
        result = stop()
        coerce_optional_bool(
            "stop",
            result,
            f"Componente '{component_name}' retornou False em stop()",
        )
    except Exception as exc:  # noqa: BLE001
        log_error(f"Falha ao finalizar componente '{component_name}': {exc}")


def normalize_read_snapshot(
    raw_value: Any,
    plant: PlantContext,
) -> tuple[SensorPayload, ActuatorPayload]:
    if raw_value is None:
        return {}, {}
    if not isinstance(raw_value, dict):
        raise RuntimeError(
            "read() deve retornar um objeto JSON no formato {'sensors': {...}, 'actuators': {...}}"
        )

    sensors = normalize_float_map(raw_value.get("sensors"), "read().sensors", set(plant.sensors.ids))
    actuators = normalize_float_map(raw_value.get("actuators"), "read().actuators", set(plant.actuators.ids))
    return sensors, actuators


def normalize_controller_outputs(
    raw_value: Any,
    allowed_output_ids: List[str],
    controller_name: str,
) -> ControllerOutputPayload:
    return normalize_float_map(
        raw_value,
        f"compute().outputs[{controller_name}]",
        set(allowed_output_ids),
    )


def clone_controller_params(
    params: Dict[str, ControllerParamSpec],
) -> Dict[str, ControllerParamSpec]:
    return {
        key: ControllerParamSpec(
            key=param.key,
            type=param.type,
            value=cast(JSONValue, copy.deepcopy(param.value)),
            label=param.label,
        )
        for key, param in params.items()
    }


def serialize_controller_params(
    params: Dict[str, ControllerParamSpec],
) -> Dict[str, Dict[str, JSONValue | str]]:
    return {
        key: {
            "type": param.type,
            "value": cast(JSONValue, copy.deepcopy(param.value)),
            "label": param.label,
        }
        for key, param in params.items()
    }


def build_public_controller_metadata(
    controller: ControllerMetadata,
) -> ControllerPublicMetadata:
    return ControllerPublicMetadata(
        id=controller.id,
        name=controller.name,
        controller_type=controller.controller_type,
        input_variable_ids=list(controller.input_variable_ids),
        output_variable_ids=list(controller.output_variable_ids),
        params=clone_controller_params(controller.params),
    )


def build_driver_plugin_context(bootstrap: RuntimeBootstrap) -> DriverPluginContext:
    return DriverPluginContext(
        config=cast(Dict[str, JSONValue], copy.deepcopy(bootstrap.driver.config)),
        plant=bootstrap.plant,
        logger=RuntimePluginLogger(
            source_kind="driver",
            runtime_id=bootstrap.runtime.id,
            plant_id=bootstrap.plant.id,
            plugin_id=bootstrap.driver.plugin_id,
            plugin_name=bootstrap.driver.plugin_name,
        ),
    )


def build_controller_plugin_context(
    controller: ControllerMetadata,
    plant: PlantContext,
    runtime_id: str,
) -> ControllerPluginContext:
    return ControllerPluginContext(
        controller=build_public_controller_metadata(controller),
        plant=plant,
        logger=RuntimePluginLogger(
            source_kind="controller",
            runtime_id=runtime_id,
            plant_id=plant.id,
            plugin_id=controller.plugin_id,
            plugin_name=controller.plugin_name,
            controller_id=controller.id,
            controller_name=controller.name,
        ),
    )


def build_controller_snapshot(
    cycle_id: int,
    cycle_started_at: float,
    dt_ms: float,
    plant: PlantContext,
    controller_public_metadata: Dict[str, Any],
    sensors: SensorPayload,
    actuators: ActuatorPayload,
) -> Dict[str, Any]:
    return {
        "cycle_id": cycle_id,
        "timestamp": cycle_started_at,
        "dt_s": max(0.0, dt_ms / 1000.0),
        "plant": {
            "id": plant.id,
            "name": plant.name,
        },
        "setpoints": dict(plant.setpoints),
        "sensors": dict(sensors),
        "actuators": dict(actuators),
        "variables_by_id": {
            variable_id: {
                "id": variable.id,
                "name": variable.name,
                "type": variable.type,
                "unit": variable.unit,
                "setpoint": variable.setpoint,
                "pv_min": variable.pv_min,
                "pv_max": variable.pv_max,
                "linked_sensor_ids": list(variable.linked_sensor_ids),
            }
            for variable_id, variable in plant.variables_by_id.items()
        },
        "controller": copy.deepcopy(controller_public_metadata),
    }


def spawn_command_reader(command_queue: "queue.Queue[Dict[str, Any]]") -> None:
    def _reader() -> None:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception as exc:  # noqa: BLE001
                emit("error", {"message": f"Comando JSON inválido: {exc}"})
                continue

            if not isinstance(payload, dict):
                emit("error", {"message": "Comando recebido deve ser um objeto JSON"})
                continue

            command_queue.put(cast(Dict[str, Any], payload))

    thread = threading.Thread(target=_reader, daemon=True, name="stdin-command-reader")
    thread.start()


def bootstrap_from_file(bootstrap_path: Path) -> RuntimeBootstrap:
    with bootstrap_path.open("r", encoding="utf-8") as handle:
        return normalize_bootstrap(json.load(handle))


def handle_command(command: Dict[str, Any], engine: PlantRuntimeEngine) -> None:
    msg_type = str(command.get("type", "")).strip()
    payload = command.get("payload")

    if msg_type == "init":
        engine.apply_init(normalize_bootstrap(payload))
        return

    if msg_type == "start":
        engine.start()
        emit(
            "connected",
            {"runtime_id": engine.runtime_id, "plant_id": engine.plant_id},
        )
        return

    if msg_type == "pause":
        engine.pause()
        return

    if msg_type == "resume":
        engine.resume()
        return

    if msg_type == "update_setpoints":
        raw_payload = expect_dict(payload, "update_setpoints.payload")
        setpoints = normalize_float_map(
            raw_payload.get("setpoints"),
            "update_setpoints.payload.setpoints",
        )
        engine.update_setpoints(setpoints)
        return

    if msg_type == "update_controllers":
        raw_payload = expect_dict(payload, "update_controllers.payload")
        controllers_raw = raw_payload.get("controllers")
        if controllers_raw is None:
            controllers: List[ControllerMetadata] = []
        elif not isinstance(controllers_raw, list):
            raise RuntimeError("update_controllers.payload.controllers deve ser um array")
        else:
            controllers = [
                normalize_controller_metadata(controller_raw, index)
                for index, controller_raw in enumerate(controllers_raw)
            ]
        try:
            engine.update_controllers(controllers)
        except Exception as exc:  # noqa: BLE001
            log_exception(exc)
            emit("error", {"message": f"Falha ao atualizar controladores: {exc}"})
        return

    if msg_type in ("stop", "shutdown"):
        engine.request_shutdown()
        return

    if msg_type == "write_outputs":
        emit("warning", {"message": "Comando write_outputs não é suportado nesta fase"})
        return


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--bootstrap", required=True)
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    bootstrap_path = Path(args.bootstrap)

    bootstrap_protocol_stdout()

    if not bootstrap_path.exists():
        emit("error", {"message": f"bootstrap.json não encontrado em '{bootstrap_path}'"})
        return 1

    bootstrap = bootstrap_from_file(bootstrap_path)
    engine = PlantRuntimeEngine(bootstrap)
    command_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    spawn_command_reader(command_queue)

    emit(
        "ready",
        {
            "runtime_id": engine.runtime_id,
            "plant_id": engine.plant_id,
            "driver": engine.bootstrap.driver.plugin_name,
            "runtime_dir": str(runtime_dir),
        },
    )

    try:
        while not engine.should_exit:
            wait_timeout = engine.next_wait_timeout()
            try:
                command = command_queue.get(timeout=0.5 if wait_timeout is None else wait_timeout)
                try:
                    handle_command(command, engine)
                except Exception as exc:  # noqa: BLE001
                    log_exception(exc)
                    emit("error", {"message": f"Falha ao processar comando '{command.get('type', '')}': {exc}"})
                    engine.request_shutdown()
                    continue
            except queue.Empty:
                pass

            while not engine.should_exit:
                try:
                    command = command_queue.get_nowait()
                except queue.Empty:
                    break

                try:
                    handle_command(command, engine)
                except Exception as exc:  # noqa: BLE001
                    log_exception(exc)
                    emit("error", {"message": f"Falha ao processar comando '{command.get('type', '')}': {exc}"})
                    engine.request_shutdown()
                    break

            if engine.should_exit:
                break

            engine.apply_pending_controller_reload()
            engine.run_cycle()
    finally:
        engine.stop()

    emit("stopped", {"runtime_id": engine.runtime_id, "plant_id": engine.plant_id})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:  # noqa: BLE001
        log_exception(exc)
        emit("error", {"message": f"Runner Python falhou: {exc}"})
        raise
