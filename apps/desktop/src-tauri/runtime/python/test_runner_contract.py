from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
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

    def test_driver_context_exposes_only_config_and_plant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_bootstrap(Path(tmp_dir))
            context = runner.build_driver_plugin_context(bootstrap)

        self.assertEqual(set(vars(context).keys()), {"config", "plant"})
        self.assertFalse(hasattr(context, "runtime"))

    def test_controller_context_uses_minimum_public_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bootstrap = self.build_bootstrap(Path(tmp_dir))
            context = runner.build_controller_plugin_context(
                bootstrap.controllers[0],
                bootstrap.plant,
            )

        self.assertEqual(set(vars(context).keys()), {"controller", "plant"})
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
                self.assertEqual(driver_instance.context_keys, {"config", "plant"})
                self.assertFalse(hasattr(driver_instance.context, "runtime"))

                self.assertEqual(len(engine.controllers), 1)
                controller_instance = engine.controllers[0].instance
                self.assertEqual(controller_instance.context_keys, {"controller", "plant"})
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

    def test_engine_uptime_progresses_from_first_cycle_start(self) -> None:
        class FakeClock:
            def __init__(self) -> None:
                self.monotonic_now = 1000.0
                self.wall_now = 1700000000.0

            def monotonic(self) -> float:
                return self.monotonic_now

            def time(self) -> float:
                return self.wall_now + (self.monotonic_now - 1000.0)

            def sleep(self, duration: float) -> None:
                self.monotonic_now += max(0.0, duration)

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
                patch.object(runner.time, "monotonic", fake_clock.monotonic),
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
