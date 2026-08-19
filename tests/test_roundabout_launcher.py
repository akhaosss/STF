import copy
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

from scripts.roundabout_launcher import (
    ConfigError,
    editor_command,
    load_config,
    prepare_formal_scenarios,
    run_command,
    validate_formal_run,
    wait_for_carla,
)
from tests.test_roundabout_2b import valid_config


class RoundaboutLauncherTest(unittest.TestCase):
    def test_repository_yaml_loads_and_drives_editor_command(self):
        config = load_config()
        self.assertEqual(config["conda_env"], "carla0916")
        self.assertEqual(config["host"], "127.0.0.1")
        self.assertEqual(config["port"], 2000)
        command = editor_command(config, "SafeBenchHK")
        self.assertIn("--scenario", command)
        self.assertIn("2b", command)
        self.assertIn("SafeBenchHK", command)
        self.assertNotIn("--roundabout_speed_limit_kmh", command)
        self.assertIn("--roundabout_variants_json", command)
        self.assertEqual(config["conflict_headway_s"], 1.0)
        self.assertEqual(config["conflict_tolerance_s"], 0.5)
        self.assertIn("--roundabout_conflict_headway_s", command)
        self.assertIn("--roundabout_conflict_tolerance_s", command)
        self.assertEqual(len(config["roundabout_variants"]["weather"]), 120)
        self.assertEqual(len(config["roundabout_variants"]["vehicles"]), 8)

    def test_formal_launcher_expands_one_scene_definition_to_three_trials(self):
        config = copy.copy(load_config())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "definitions"
            source_dir.mkdir()
            config["input_dir"] = source_dir
            config["experiment_root"] = root / "runs"
            scenario = valid_config()
            scenario["roundabout_test"].pop("reproducibility", None)
            scenario["name"] = "scenario_2b_route_clear_tesla"
            source = source_dir / "scenario_2b_route_clear_tesla.json"
            source.write_text(
                __import__("json").dumps(
                    {"FakeTown": {"route_01": [scenario]}}),
                encoding="utf-8")

            prepared_dir, paths = prepare_formal_scenarios(
                config, [source], "FakeTown")

            self.assertEqual(len(paths), 3)
            self.assertTrue(prepared_dir.is_dir())
            self.assertEqual(
                {__import__("json").loads(path.read_text(encoding="utf-8"))
                 ["FakeTown"]["route_01"][0]["roundabout_test"]
                 ["reproducibility"]["trial_index"] for path in paths},
                {1, 2, 3})

    def test_behavior_and_tcp_commands_use_separate_result_roots(self):
        config = load_config()
        config = copy.copy(config)
        config["tcp_model_path"] = Path("/tmp/model.ckpt")
        behavior = run_command(config, "SafeBenchHK", "behavior")
        tcp = run_command(config, "SafeBenchHK", "tcp")
        behavior_video = behavior[behavior.index("--video_dir") + 1]
        tcp_video = tcp[tcp.index("--video_dir") + 1]
        self.assertNotEqual(behavior_video, tcp_video)
        self.assertTrue(behavior_video.endswith("/behavior"))
        self.assertTrue(tcp_video.endswith("/tcp"))
        self.assertNotIn("--model_path", behavior)
        self.assertIn("--model_path", tcp)
        self.assertIn("--host", behavior)
        self.assertIn("--port", behavior)

    def test_behavior_screening_runs_definitions_once_in_separate_output(self):
        config = load_config()
        command = run_command(
            config, "SafeBenchHK", "behavior", screening=True)
        self.assertIn("--screening", command)
        self.assertEqual(
            command[command.index("--max_invalid_retries") + 1], "0")
        video_dir = command[command.index("--video_dir") + 1]
        self.assertTrue(video_dir.endswith("/roundabout_screening/behavior"))
        self.assertNotIn("--model_path", command)

    def test_formal_pair_is_rejected_before_behavior_when_tcp_is_unset(self):
        config = copy.copy(load_config())
        with tempfile.TemporaryDirectory() as directory:
            input_dir = Path(directory)
            for index in range(1, 4):
                (input_dir / "scenario_2b_trial_{:02d}.json".format(index)).write_text(
                    "{}", encoding="utf-8")
            config["input_dir"] = input_dir
            config["tcp_model_path"] = None
            with self.assertRaisesRegex(ConfigError, "TCP checkpoint"):
                validate_formal_run(config)

    def test_behavior_only_does_not_require_tcp_checkpoint(self):
        config = copy.copy(load_config())
        with tempfile.TemporaryDirectory() as directory:
            input_dir = Path(directory)
            (input_dir / "scenario_2b_definition.json").write_text(
                "{}", encoding="utf-8")
            config["input_dir"] = input_dir
            config["tcp_model_path"] = None
            paths = validate_formal_run(config, models=("behavior",))
            self.assertEqual(len(paths), 1)

    def test_carla_timeout_is_immediately_visible_and_actionable(self):
        class UnavailableClient:
            def set_timeout(self, _seconds):
                pass

            def get_world(self):
                raise RuntimeError("simulator unavailable")

        fake_carla = types.SimpleNamespace(
            Client=lambda _host, _port: UnavailableClient())
        config = copy.copy(load_config())
        config["wait_timeout_s"] = 0
        output = io.StringIO()
        with mock.patch.dict(sys.modules, {"carla": fake_carla}), \
                contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(ConfigError, "请先启动CARLA"):
                wait_for_carla(config)

        self.assertIn("正在连接 CARLA 127.0.0.1:2000", output.getvalue())


if __name__ == "__main__":
    unittest.main()
