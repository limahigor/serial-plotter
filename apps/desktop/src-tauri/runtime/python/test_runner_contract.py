from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from types import ModuleType
from typing import Any


def load_runner_module() -> ModuleType:
    runner_path = Path(__file__).with_name("runner.py")
    spec = importlib.util.spec_from_file_location("senamby_runtime_runner", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Falha ao carregar runner.py para testes")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = load_runner_module()


def run_runner_subprocess(snippet: str) -> subprocess.CompletedProcess[str]:
    runner_path = Path(__file__).with_name("runner.py")
    script = "\n".join(
        [
            "import importlib.util",
            "import sys",
            "from pathlib import Path",
            "",
            f"runner_path = Path({str(runner_path)!r})",
            'spec = importlib.util.spec_from_file_location("senamby_runtime_runner_subprocess", runner_path)',
            "if spec is None or spec.loader is None:",
            '    raise RuntimeError("Falha ao carregar runner.py no subprocesso")',
            "",
            "runner = importlib.util.module_from_spec(spec)",
            "sys.modules[spec.name] = runner",
            "spec.loader.exec_module(runner)",
            "",
            textwrap.dedent(snippet).strip(),
            "",
        ]
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def parse_protocol_lines(raw_stdout: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in raw_stdout.splitlines() if line.strip()]


class FakeClock:
    def __init__(
        self,
        *,
        start_ns: int = 1_000_000_000_000,
        wall_now: float = 1_700_000_000.0,
        sleep_overshoot_ns: int = 0,
        yield_step_ns: int = 250_000,
    ) -> None:
        self.start_ns = start_ns
        self.monotonic_now_ns = start_ns
        self.wall_now = wall_now
        self.sleep_overshoot_ns = sleep_overshoot_ns
        self.yield_step_ns = yield_step_ns

    def monotonic_ns(self) -> int:
        return self.monotonic_now_ns

    def time(self) -> float:
        return self.wall_now + (
            (self.monotonic_now_ns - self.start_ns) / runner.NANOSECONDS_PER_SECOND
        )

    def sleep(self, duration: float) -> None:
        duration_ns = max(0, int(duration * runner.NANOSECONDS_PER_SECOND))
        if duration_ns > 0:
            self.monotonic_now_ns += duration_ns + self.sleep_overshoot_ns
            return

        self.monotonic_now_ns += self.yield_step_ns


class RunnerContractTests(unittest.TestCase):
    def build_bootstrap(self, root: Path) -> Any:
        plant_variables = [
            runner.VariableSpec(
                id="sensor_1",
                name="Sensor 1",
                type="sensor",
                unit="C",
                setpoint=42.0,
                pv_min=0.0,
                pv_max=100.0,
                linked_sensor_ids=[],
            ),
            runner.VariableSpec(
                id="actuator_1",
                name="Actuator 1",
                type="actuator",
                unit="%",
                setpoint=0.0,
                pv_min=0.0,
                pv_max=100.0,
                linked_sensor_ids=["sensor_1"],
            ),
        ]

        variables_by_id = {variable.id: variable for variable in plant_variables}
        plant = runner.PlantContext(
            id="plant_1",
            name="Plant 1",
            variables=plant_variables,
            variables_by_id=variables_by_id,
            sensors=runner.IOGroup(
                ids=["sensor_1"],
                count=1,
                variables=[variables_by_id["sensor_1"]],
                variables_by_id={"sensor_1": variables_by_id["sensor_1"]},
            ),
            actuators=runner.IOGroup(
                ids=["actuator_1"],
                count=1,
                variables=[variables_by_id["actuator_1"]],
                variables_by_id={"actuator_1": variables_by_id["actuator_1"]},
            ),
            setpoints={"sensor_1": 42.0, "actuator_1": 0.0},
        )

        runtime = runner.RuntimeContext(
            id="rt_1",
            timing=runner.RuntimeTiming(
                owner="runtime",
                clock="monotonic",
                strategy="deadline",
                sample_time_ms=100,
            ),
            supervision=runner.RuntimeSupervision(
                owner="rust",
                startup_timeout_ms=12000,
                shutdown_timeout_ms=4000,
            ),
            paths=runner.RuntimePaths(
                runtime_dir=str(root / "runtime"),
                venv_python_path=str(root / ".venv" / "bin" / "python"),
                runner_path=str(root / "runtime" / "runner.py"),
                bootstrap_path=str(root / "runtime" / "bootstrap.json"),
            ),
        )

        driver_dir = root / "driver_plugin"
        driver_dir.mkdir()
        (driver_dir / "main.py").write_text(
            textwrap.dedent(
                """
                from typing import Any, Dict

                class ContractDriver:
                    def __init__(self, context: Any) -> None:
                        if hasattr(context, "runtime"):
                            raise RuntimeError("driver context leaked runtime")
                        self.context = context
                        self.context_keys = set(vars(context).keys())

                    def connect(self) -> bool:
                        return True

                    def stop(self) -> bool:
                        return True

                    def read(self) -> Dict[str, Dict[str, float]]:
                        return {
                            "sensors": {"sensor_1": 1.0},
                            "actuators": {"actuator_1": 0.0},
                        }

                    def write(self, outputs: Dict[str, float]) -> bool:
                        return True
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        controller_dir = root / "controller_plugin"
        controller_dir.mkdir()
        (controller_dir / "main.py").write_text(
            textwrap.dedent(
                """
                from typing import Any, Dict

                class ContractController:
                    def __init__(self, context: Any) -> None:
                        if hasattr(context, "runtime"):
                            raise RuntimeError("controller context leaked runtime")
                        self.context = context
                        self.context_keys = set(vars(context).keys())
                        self.controller_keys = set(vars(context.controller).keys())

                    def connect(self) -> bool:
                        return True

                    def stop(self) -> bool:
                        return True

                    def compute(self, snapshot: Dict[str, Any]) -> Dict[str, float]:
                        return {self.context.controller.output_variable_ids[0]: 0.0}
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        return runner.RuntimeBootstrap(
            driver=runner.DriverMetadata(
                plugin_id="driver_plugin",
                plugin_name="Driver Plugin",
                plugin_dir=str(driver_dir),
                source_file="main.py",
                class_name="ContractDriver",
                config={"port": "COM1"},
            ),
            controllers=[
                runner.ControllerMetadata(
                    id="ctrl_1",
                    plugin_id="controller_plugin",
                    plugin_name="Controller Plugin",
                    plugin_dir=str(controller_dir),
                    source_file="main.py",
                    class_name="ContractController",
                    name="Controller 1",
                    controller_type="PID",
                    active=True,
                    input_variable_ids=["sensor_1"],
                    output_variable_ids=["actuator_1"],
                    params={
                        "kp": runner.ControllerParamSpec(
                            key="kp",
                            type="number",
                            value=1.2,
                            label="Kp",
                        )
                    },
                )
            ],
            plant=plant,
            runtime=runtime,
        )

    def build_multi_channel_bootstrap(self, root: Path) -> Any:
        plant_variables = [
            runner.VariableSpec(
                id="sensor_1",
                name="Sensor 1",
                type="sensor",
                unit="C",
                setpoint=42.0,
                pv_min=0.0,
                pv_max=100.0,
                linked_sensor_ids=[],
            ),
            runner.VariableSpec(
                id="sensor_2",
                name="Sensor 2",
                type="sensor",
                unit="C",
                setpoint=35.0,
                pv_min=0.0,
                pv_max=100.0,
                linked_sensor_ids=[],
            ),
            runner.VariableSpec(
                id="actuator_1",
                name="Actuator 1",
                type="actuator",
                unit="%",
                setpoint=0.0,
                pv_min=0.0,
                pv_max=100.0,
                linked_sensor_ids=["sensor_1"],
            ),
            runner.VariableSpec(
                id="actuator_2",
                name="Actuator 2",
                type="actuator",
                unit="%",
                setpoint=0.0,
                pv_min=0.0,
                pv_max=100.0,
                linked_sensor_ids=["sensor_2"],
            ),
        ]

        variables_by_id = {variable.id: variable for variable in plant_variables}
        plant = runner.PlantContext(
            id="plant_multi",
            name="Plant Multi",
            variables=plant_variables,
            variables_by_id=variables_by_id,
            sensors=runner.IOGroup(
                ids=["sensor_1", "sensor_2"],
                count=2,
                variables=[variables_by_id["sensor_1"], variables_by_id["sensor_2"]],
                variables_by_id={
                    "sensor_1": variables_by_id["sensor_1"],
                    "sensor_2": variables_by_id["sensor_2"],
                },
            ),
            actuators=runner.IOGroup(
                ids=["actuator_1", "actuator_2"],
                count=2,
                variables=[variables_by_id["actuator_1"], variables_by_id["actuator_2"]],
                variables_by_id={
                    "actuator_1": variables_by_id["actuator_1"],
                    "actuator_2": variables_by_id["actuator_2"],
                },
            ),
            setpoints={
                "sensor_1": 42.0,
                "sensor_2": 35.0,
                "actuator_1": 0.0,
                "actuator_2": 0.0,
            },
        )

        runtime = runner.RuntimeContext(
            id="rt_multi",
            timing=runner.RuntimeTiming(
                owner="runtime",
                clock="monotonic",
                strategy="deadline",
                sample_time_ms=100,
            ),
            supervision=runner.RuntimeSupervision(
                owner="rust",
                startup_timeout_ms=12000,
                shutdown_timeout_ms=4000,
            ),
            paths=runner.RuntimePaths(
                runtime_dir=str(root / "runtime"),
                venv_python_path=str(root / ".venv" / "bin" / "python"),
                runner_path=str(root / "runtime" / "runner.py"),
                bootstrap_path=str(root / "runtime" / "bootstrap.json"),
            ),
        )

        driver_dir = root / "driver_plugin"
        driver_dir.mkdir()
        (driver_dir / "main.py").write_text(
            textwrap.dedent(
                """
                from typing import Any, Dict

                class MultiChannelDriver:
                    def __init__(self, context: Any) -> None:
                        self.context = context
                        self.write_calls = []

                    def connect(self) -> bool:
                        return True

                    def stop(self) -> bool:
                        return True

                    def read(self) -> Dict[str, Dict[str, float]]:
                        return {
                            "sensors": {"sensor_1": 10.0, "sensor_2": 20.0},
                            "actuators": {"actuator_1": 0.0, "actuator_2": 0.0},
                        }

                    def write(self, outputs: Dict[str, float]) -> bool:
                        self.write_calls.append(dict(outputs))
                        return True
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        controller_dir = root / "controller_plugin"
        controller_dir.mkdir()
        (controller_dir / "main.py").write_text(
            textwrap.dedent(
                """
                from typing import Any, Dict

                class CounterController:
                    def __init__(self, context: Any) -> None:
                        self.context = context
                        self.connect_calls = 0
                        self.stop_calls = 0

                    def connect(self) -> bool:
                        self.connect_calls += 1
                        return True

                    def stop(self) -> bool:
                        self.stop_calls += 1
                        return True

                    def compute(self, snapshot: Dict[str, Any]) -> Dict[str, float]:
                        output_id = self.context.controller.output_variable_ids[0]
                        sensor_id = self.context.controller.input_variable_ids[0]
                        return {
                            output_id: float(snapshot["sensors"].get(sensor_id, 0.0))
                        }
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        return runner.RuntimeBootstrap(
            driver=runner.DriverMetadata(
                plugin_id="driver_plugin_multi",
                plugin_name="Driver Plugin Multi",
                plugin_dir=str(driver_dir),
                source_file="main.py",
                class_name="MultiChannelDriver",
                config={},
            ),
            controllers=[
                runner.ControllerMetadata(
                    id="ctrl_1",
                    plugin_id="controller_plugin_multi",
                    plugin_name="Controller Plugin Multi",
                    plugin_dir=str(controller_dir),
                    source_file="main.py",
                    class_name="CounterController",
                    name="Controller 1",
                    controller_type="PID",
                    active=True,
                    input_variable_ids=["sensor_1"],
                    output_variable_ids=["actuator_1"],
                    params={},
                )
            ],
            plant=plant,
            runtime=runtime,
        )

    def test_driver_context_exposes_only_config_and_plant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_bootstrap(Path(tmp_dir))
            context = runner.build_driver_plugin_context(bootstrap)

        self.assertEqual(set(vars(context).keys()), {"config", "plant", "logger"})
        self.assertFalse(hasattr(context, "runtime"))

    def test_controller_context_uses_minimum_public_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_bootstrap(Path(tmp_dir))
            context = runner.build_controller_plugin_context(
                bootstrap.controllers[0],
                bootstrap.plant,
                bootstrap.runtime.id,
            )

        self.assertEqual(set(vars(context).keys()), {"controller", "plant", "logger"})
        self.assertFalse(hasattr(context, "runtime"))
        self.assertEqual(
            set(vars(context.controller).keys()),
            {
                "id",
                "name",
                "controller_type",
                "input_variable_ids",
                "output_variable_ids",
                "params",
            },
        )

    def test_snapshot_controller_omits_internal_loader_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_bootstrap(Path(tmp_dir))
            snapshot = runner.build_controller_snapshot(
                cycle_id=1,
                cycle_started_at=123.456,
                dt_ms=100.0,
                plant=bootstrap.plant,
                controller_public_metadata=runner.build_public_controller_metadata(
                    bootstrap.controllers[0]
                ).serialize(),
                sensors={"sensor_1": 40.0},
                actuators={"actuator_1": 10.0},
            )

        self.assertEqual(
            set(snapshot["controller"].keys()),
            {
                "id",
                "name",
                "controller_type",
                "input_variable_ids",
                "output_variable_ids",
                "params",
            },
        )
        self.assertNotIn("plugin_id", snapshot["controller"])
        self.assertNotIn("plugin_name", snapshot["controller"])
        self.assertNotIn("active", snapshot["controller"])

    def test_engine_loads_plugins_with_internal_bootstrap_and_public_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_bootstrap(Path(tmp_dir))
            engine = runner.PlantRuntimeEngine(bootstrap)
            try:
                engine.start()

                driver_instance = engine.driver_instance
                self.assertIsNotNone(driver_instance)
                self.assertEqual(driver_instance.context_keys, {"config", "plant", "logger"})
                self.assertFalse(hasattr(driver_instance.context, "runtime"))

                self.assertEqual(len(engine.controllers), 1)
                controller_instance = engine.controllers[0].instance
                self.assertEqual(
                    controller_instance.context_keys,
                    {"controller", "plant", "logger"},
                )
                self.assertFalse(hasattr(controller_instance.context, "runtime"))
                self.assertEqual(
                    controller_instance.controller_keys,
                    {
                        "id",
                        "name",
                        "controller_type",
                        "input_variable_ids",
                        "output_variable_ids",
                        "params",
                    },
                )
            finally:
                engine.stop()

    def test_runtime_logger_emits_structured_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_bootstrap(Path(tmp_dir))
            driver_context = runner.build_driver_plugin_context(bootstrap)
            controller_context = runner.build_controller_plugin_context(
                bootstrap.controllers[0],
                bootstrap.plant,
                bootstrap.runtime.id,
            )

        with patch.object(runner, "emit") as emit_mock:
            driver_context.logger.info("driver ok", {"phase": "connect"})
            controller_context.logger.warning("controller late", {"dt_ms": 125.0})

        self.assertEqual(emit_mock.call_count, 2)
        first_call = emit_mock.call_args_list[0]
        self.assertEqual(first_call.args[0], "log")
        self.assertEqual(first_call.args[1]["level"], "info")
        self.assertEqual(first_call.args[1]["source_kind"], "driver")
        self.assertEqual(first_call.args[1]["plugin_id"], bootstrap.driver.plugin_id)
        self.assertEqual(first_call.args[1]["details"], {"phase": "connect"})

        second_call = emit_mock.call_args_list[1]
        self.assertEqual(second_call.args[1]["level"], "warning")
        self.assertEqual(second_call.args[1]["source_kind"], "controller")
        self.assertEqual(
            second_call.args[1]["controller_id"],
            bootstrap.controllers[0].id,
        )

    def test_engine_enriches_legacy_controller_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_bootstrap(Path(tmp_dir))
            controller_path = Path(bootstrap.controllers[0].plugin_dir) / "main.py"
            controller_path.write_text(
                textwrap.dedent(
                    """
                    from typing import Any, Dict

                    class InnerLoop:
                        def __init__(self) -> None:
                            self.loop_name = "inner-loop"

                    class CompatibilityController:
                        def __init__(self, context: Any) -> None:
                            self.context = context
                            self.controller = InnerLoop()

                        def compute(self, snapshot: Dict[str, Any]) -> Dict[str, float]:
                            return {self.controller.output_variable_ids[0]: 0.0}
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            bootstrap.controllers[0].class_name = "CompatibilityController"
            engine = runner.PlantRuntimeEngine(bootstrap)
            try:
                engine.start()

                controller_instance = engine.controllers[0].instance
                self.assertEqual(controller_instance.controller.loop_name, "inner-loop")
                self.assertEqual(
                    controller_instance.controller.output_variable_ids,
                    ["actuator_1"],
                )

                snapshot = runner.build_controller_snapshot(
                    cycle_id=1,
                    cycle_started_at=123.456,
                    dt_ms=100.0,
                    plant=bootstrap.plant,
                    controller_public_metadata=runner.build_public_controller_metadata(
                        bootstrap.controllers[0]
                    ).serialize(),
                    sensors={"sensor_1": 40.0},
                    actuators={"actuator_1": 10.0},
                )

                self.assertEqual(
                    controller_instance.compute(snapshot),
                    {"actuator_1": 0.0},
                )
            finally:
                engine.stop()

    def test_load_plugin_class_supports_plugins_with_dataclass_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            plugin_dir = Path(tmp_dir)
            (plugin_dir / "main.py").write_text(
                textwrap.dedent(
                    """
                    from dataclasses import dataclass

                    @dataclass
                    class HelperState:
                        value: int = 1

                    class DataclassDriver:
                        def __init__(self, context):
                            self.context = context
                            self.state = HelperState()

                        def connect(self):
                            return True

                        def stop(self):
                            return True

                        def read(self):
                            return {"sensors": {}, "actuators": {}}
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            plugin_cls = runner.load_plugin_class(
                plugin_dir,
                "main.py",
                "DataclassDriver",
                runner.DRIVER_REQUIRED_METHODS,
                "driver de teste",
            )
            instance = runner.instantiate_plugin(
                plugin_cls,
                object(),
                "driver de teste",
            )

            self.assertEqual(plugin_cls.__name__, "DataclassDriver")
            self.assertEqual(instance.state.value, 1)

    def test_update_controllers_preserves_running_instances_that_did_not_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_multi_channel_bootstrap(Path(tmp_dir))
            engine = runner.PlantRuntimeEngine(bootstrap)
            try:
                engine.start()

                first_loaded = engine.controllers[0]
                first_instance = first_loaded.instance
                self.assertEqual(first_instance.connect_calls, 1)

                next_controllers = [
                    first_loaded.metadata,
                    runner.ControllerMetadata(
                        id="ctrl_2",
                        plugin_id="controller_plugin_multi",
                        plugin_name="Controller Plugin Multi",
                        plugin_dir=first_loaded.metadata.plugin_dir,
                        source_file=first_loaded.metadata.source_file,
                        class_name=first_loaded.metadata.class_name,
                        name="Controller 2",
                        controller_type="PID",
                        active=True,
                        input_variable_ids=["sensor_2"],
                        output_variable_ids=["actuator_2"],
                        params={},
                    ),
                ]

                engine.update_controllers(next_controllers)

                for _ in range(50):
                    time.sleep(0.01)
                    engine.apply_pending_controller_reload()
                    if len(engine.controllers) == 2:
                        break

                self.assertEqual(len(engine.controllers), 2)
                self.assertIs(engine.controllers[0].instance, first_instance)
                self.assertEqual(first_instance.connect_calls, 1)
                self.assertEqual(first_instance.stop_calls, 0)
                self.assertEqual(engine.controllers[1].instance.connect_calls, 1)
            finally:
                engine.stop()

    def test_update_controllers_preserves_instance_when_only_params_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_multi_channel_bootstrap(Path(tmp_dir))
            bootstrap.controllers[0].params = {
                "kp": runner.ControllerParamSpec(
                    key="kp",
                    type="number",
                    value=1.0,
                    label="Kp",
                )
            }
            engine = runner.PlantRuntimeEngine(bootstrap)
            try:
                engine.start()

                first_loaded = engine.controllers[0]
                first_instance = first_loaded.instance
                self.assertEqual(first_instance.connect_calls, 1)

                next_controllers = [
                    runner.ControllerMetadata(
                        id=first_loaded.metadata.id,
                        plugin_id=first_loaded.metadata.plugin_id,
                        plugin_name=first_loaded.metadata.plugin_name,
                        plugin_dir=first_loaded.metadata.plugin_dir,
                        source_file=first_loaded.metadata.source_file,
                        class_name=first_loaded.metadata.class_name,
                        name="Controller 1 Tuned",
                        controller_type="PI",
                        active=True,
                        input_variable_ids=list(first_loaded.metadata.input_variable_ids),
                        output_variable_ids=list(first_loaded.metadata.output_variable_ids),
                        params={
                            "kp": runner.ControllerParamSpec(
                                key="kp",
                                type="number",
                                value=2.5,
                                label="Kp",
                            )
                        },
                    )
                ]

                engine.update_controllers(next_controllers)

                for _ in range(50):
                    time.sleep(0.01)
                    engine.apply_pending_controller_reload()
                    if engine.controllers[0].metadata.params["kp"].value == 2.5:
                        break

                self.assertEqual(len(engine.controllers), 1)
                self.assertIs(engine.controllers[0].instance, first_instance)
                self.assertEqual(first_instance.connect_calls, 1)
                self.assertEqual(first_instance.stop_calls, 0)
                self.assertEqual(engine.controllers[0].metadata.name, "Controller 1 Tuned")
                self.assertEqual(engine.controllers[0].metadata.controller_type, "PI")
                self.assertEqual(engine.controllers[0].metadata.params["kp"].value, 2.5)
                self.assertEqual(
                    engine.controllers[0].instance.context.controller.params["kp"].value,
                    2.5,
                )
            finally:
                engine.stop()

    def test_run_cycle_writes_distinct_outputs_for_distinct_controller_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_multi_channel_bootstrap(Path(tmp_dir))
            bootstrap = runner.RuntimeBootstrap(
                driver=bootstrap.driver,
                controllers=[
                    bootstrap.controllers[0],
                    runner.ControllerMetadata(
                        id="ctrl_2",
                        plugin_id="controller_plugin_multi",
                        plugin_name="Controller Plugin Multi",
                        plugin_dir=bootstrap.controllers[0].plugin_dir,
                        source_file=bootstrap.controllers[0].source_file,
                        class_name=bootstrap.controllers[0].class_name,
                        name="Controller 2",
                        controller_type="PID",
                        active=True,
                        input_variable_ids=["sensor_2"],
                        output_variable_ids=["actuator_2"],
                        params={},
                    ),
                ],
                plant=bootstrap.plant,
                runtime=bootstrap.runtime,
            )
            engine = runner.PlantRuntimeEngine(bootstrap)
            try:
                engine.start()
                engine.run_cycle()

                driver_instance = engine.driver_instance
                self.assertIsNotNone(driver_instance)
                self.assertEqual(
                    driver_instance.write_calls[-1],
                    {"actuator_1": 10.0, "actuator_2": 20.0},
                )
            finally:
                engine.stop()

    def test_engine_uptime_progresses_from_first_cycle_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_bootstrap = self.build_bootstrap(Path(tmp_dir))
            bootstrap = runner.RuntimeBootstrap(
                driver=original_bootstrap.driver,
                controllers=original_bootstrap.controllers,
                plant=original_bootstrap.plant,
                runtime=runner.RuntimeContext(
                    id=original_bootstrap.runtime.id,
                    timing=runner.RuntimeTiming(
                        owner=original_bootstrap.runtime.timing.owner,
                        clock=original_bootstrap.runtime.timing.clock,
                        strategy=original_bootstrap.runtime.timing.strategy,
                        sample_time_ms=1000,
                    ),
                    supervision=original_bootstrap.runtime.supervision,
                    paths=original_bootstrap.runtime.paths,
                ),
            )
            engine = runner.PlantRuntimeEngine(bootstrap)
            fake_clock = FakeClock()
            telemetry_payloads: list[dict[str, Any]] = []

            def capture_emit(msg_type: str, payload: dict[str, Any] | None = None) -> None:
                if msg_type == "telemetry" and payload is not None:
                    telemetry_payloads.append(payload)

            with (
                patch.object(runner.time, "monotonic_ns", fake_clock.monotonic_ns),
                patch.object(runner.time, "time", fake_clock.time),
                patch.object(runner.time, "sleep", fake_clock.sleep),
                patch.object(runner, "emit", capture_emit),
            ):
                try:
                    engine.start()
                    engine.run_cycle()
                    engine.run_cycle()
                    engine.run_cycle()
                finally:
                    engine.stop()

            self.assertEqual(len(telemetry_payloads), 3)
            self.assertAlmostEqual(telemetry_payloads[0]["uptime_s"], 0.0, places=6)
            self.assertAlmostEqual(telemetry_payloads[1]["uptime_s"], 1.0, places=6)
            self.assertAlmostEqual(telemetry_payloads[2]["uptime_s"], 2.0, places=6)

    def test_engine_effective_dt_stays_stable_with_sleep_overshoot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_bootstrap = self.build_bootstrap(Path(tmp_dir))
            bootstrap = runner.RuntimeBootstrap(
                driver=original_bootstrap.driver,
                controllers=original_bootstrap.controllers,
                plant=original_bootstrap.plant,
                runtime=runner.RuntimeContext(
                    id=original_bootstrap.runtime.id,
                    timing=runner.RuntimeTiming(
                        owner=original_bootstrap.runtime.timing.owner,
                        clock=original_bootstrap.runtime.timing.clock,
                        strategy=original_bootstrap.runtime.timing.strategy,
                        sample_time_ms=1000,
                    ),
                    supervision=original_bootstrap.runtime.supervision,
                    paths=original_bootstrap.runtime.paths,
                ),
            )
            engine = runner.PlantRuntimeEngine(bootstrap)
            fake_clock = FakeClock(sleep_overshoot_ns=4_000_000)
            telemetry_payloads: list[dict[str, Any]] = []

            def capture_emit(msg_type: str, payload: dict[str, Any] | None = None) -> None:
                if msg_type == "telemetry" and payload is not None:
                    telemetry_payloads.append(payload)

            with (
                patch.object(runner.time, "monotonic_ns", fake_clock.monotonic_ns),
                patch.object(runner.time, "time", fake_clock.time),
                patch.object(runner.time, "sleep", fake_clock.sleep),
                patch.object(runner, "emit", capture_emit),
            ):
                try:
                    engine.start()
                    engine.run_cycle()
                    engine.run_cycle()
                    engine.run_cycle()
                finally:
                    engine.stop()

            self.assertEqual(len(telemetry_payloads), 3)
            self.assertAlmostEqual(telemetry_payloads[1]["effective_dt_ms"], 1000.0, places=6)
            self.assertAlmostEqual(telemetry_payloads[2]["effective_dt_ms"], 1000.0, places=6)

    def test_engine_resume_keeps_raw_dt_and_excludes_pause_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_bootstrap = self.build_bootstrap(Path(tmp_dir))
            bootstrap = runner.RuntimeBootstrap(
                driver=original_bootstrap.driver,
                controllers=original_bootstrap.controllers,
                plant=original_bootstrap.plant,
                runtime=runner.RuntimeContext(
                    id=original_bootstrap.runtime.id,
                    timing=runner.RuntimeTiming(
                        owner=original_bootstrap.runtime.timing.owner,
                        clock=original_bootstrap.runtime.timing.clock,
                        strategy=original_bootstrap.runtime.timing.strategy,
                        sample_time_ms=1000,
                    ),
                    supervision=original_bootstrap.runtime.supervision,
                    paths=original_bootstrap.runtime.paths,
                ),
            )
            engine = runner.PlantRuntimeEngine(bootstrap)
            fake_clock = FakeClock()
            telemetry_payloads: list[dict[str, Any]] = []

            def capture_emit(msg_type: str, payload: dict[str, Any] | None = None) -> None:
                if msg_type == "telemetry" and payload is not None:
                    telemetry_payloads.append(payload)

            with (
                patch.object(runner.time, "monotonic_ns", fake_clock.monotonic_ns),
                patch.object(runner.time, "time", fake_clock.time),
                patch.object(runner.time, "sleep", fake_clock.sleep),
                patch.object(runner, "emit", capture_emit),
            ):
                try:
                    engine.start()
                    engine.run_cycle()
                    engine.pause()
                    fake_clock.sleep(5.0)
                    engine.resume()
                    engine.run_cycle()
                finally:
                    engine.stop()

            self.assertEqual(len(telemetry_payloads), 2)
            self.assertAlmostEqual(telemetry_payloads[1]["effective_dt_ms"], 1000.0, places=6)
            self.assertAlmostEqual(telemetry_payloads[1]["uptime_s"], 1.0, places=6)

    def test_next_wait_timeout_reserves_fine_window_for_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_bootstrap(Path(tmp_dir))
            engine = runner.PlantRuntimeEngine(bootstrap)
            fake_clock = FakeClock()

            with (
                patch.object(runner.time, "monotonic_ns", fake_clock.monotonic_ns),
                patch.object(runner, "emit", lambda *_args, **_kwargs: None),
            ):
                try:
                    engine.start()
                    self.assertEqual(engine.next_wait_timeout(), 0.0)

                    engine.run_cycle()
                    self.assertIsNotNone(engine.next_cycle_deadline_ns)

                    fake_clock.monotonic_now_ns = (
                        engine.next_cycle_deadline_ns - runner.FINE_SLEEP_WINDOW_NS - 1_000_000
                    )
                    timeout_before_window = engine.next_wait_timeout()
                    self.assertIsNotNone(timeout_before_window)
                    self.assertGreater(timeout_before_window or 0.0, 0.0)

                    fake_clock.monotonic_now_ns = (
                        engine.next_cycle_deadline_ns - runner.FINE_SLEEP_WINDOW_NS + 1_000_000
                    )
                    self.assertEqual(engine.next_wait_timeout(), 0.0)
                finally:
                    engine.stop()


class RunnerProtocolStreamTests(unittest.TestCase):
    def test_emit_keeps_json_on_stdout_after_bootstrap(self) -> None:
        completed = run_runner_subprocess(
            """
            runner.bootstrap_protocol_stdout()
            runner.emit("ready", {"ok": True})
            """
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual(
            parse_protocol_lines(completed.stdout),
            [{"type": "ready", "payload": {"ok": True}}],
        )
        self.assertEqual(completed.stderr.strip(), "")

    def test_python_print_is_redirected_to_stderr(self) -> None:
        completed = run_runner_subprocess(
            """
            runner.bootstrap_protocol_stdout()
            print("python-log")
            runner.emit("ready", {"ok": True})
            """
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual(
            parse_protocol_lines(completed.stdout),
            [{"type": "ready", "payload": {"ok": True}}],
        )
        self.assertIn("python-log", completed.stderr)

    @unittest.skipUnless(os.name == "posix", "Teste de libc disponível apenas em POSIX")
    def test_libc_printf_is_redirected_to_stderr(self) -> None:
        completed = run_runner_subprocess(
            """
            import ctypes

            runner.bootstrap_protocol_stdout()
            libc = ctypes.CDLL(None)
            libc.printf.argtypes = [ctypes.c_char_p]
            libc.printf.restype = ctypes.c_int
            libc.fflush.argtypes = [ctypes.c_void_p]
            libc.fflush.restype = ctypes.c_int
            libc.printf(b"native-log\\\\n")
            libc.fflush(None)
            runner.emit("ready", {"ok": True})
            """
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual(
            parse_protocol_lines(completed.stdout),
            [{"type": "ready", "payload": {"ok": True}}],
        )
        self.assertIn("native-log", completed.stderr)

    def test_emit_stays_atomic_across_threads(self) -> None:
        completed = run_runner_subprocess(
            """
            import threading

            runner.bootstrap_protocol_stdout()

            def worker(worker_id: int) -> None:
                for sequence in range(200):
                    runner.emit("telemetry", {"worker": worker_id, "sequence": sequence})

            threads = [threading.Thread(target=worker, args=(worker_id,)) for worker_id in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            """
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        lines = parse_protocol_lines(completed.stdout)

        self.assertEqual(len(lines), 1200)
        self.assertTrue(all(line["type"] == "telemetry" for line in lines))
        self.assertEqual(completed.stderr.strip(), "")


if __name__ == "__main__":
    unittest.main()
