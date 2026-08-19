import copy
import json
from pathlib import Path
import tempfile
import unittest

from roundabout_2b import validate_roundabout_config
from scripts.roundabout_launcher import load_config
from tests.test_roundabout_2b import valid_config
from tools.expand_roundabout_scenarios import discover_route_templates, expand
from weather_catalog import WEATHER_PRESET_ORDER, all_weather_profiles


class RoundaboutScenarioExpanderTest(unittest.TestCase):
    def test_shared_catalog_contains_fifteen_presets_and_120_profiles(self):
        profiles = all_weather_profiles()
        self.assertEqual(len(WEATHER_PRESET_ORDER), 15)
        self.assertEqual(len(profiles), 120)
        self.assertEqual(len({item["id"] for item in profiles}), 120)
        self.assertTrue(all("parameters" in item for item in profiles))

    def test_legacy_trials_are_deduplicated_before_small_variant_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "source"
            output_dir = root / "output"
            source_dir.mkdir()
            base = valid_config()
            for index in (1, 2, 3):
                scenario = copy.deepcopy(base)
                scenario["name"] = "scenario_2b_trial_{:02d}".format(index)
                scenario["roundabout_test"]["reproducibility"]["trial_index"] = index
                document = {"FakeTown": {"route_01": [scenario]}}
                (source_dir / "scenario_2b_trial_{:02d}.json".format(index)).write_text(
                    json.dumps(document), encoding="utf-8")

            templates = discover_route_templates(source_dir, "route_01")
            self.assertEqual(len(templates), 1)
            self.assertEqual(len(templates[0]["source_files"]), 3)

            config = copy.copy(load_config())
            config["roundabout_variants"] = {
                "weather": [
                    {"id": "clear", "parameters": {"cloudiness": 0.0}},
                    {"id": "cloudy", "parameters": {"cloudiness": 80.0}},
                ],
                "vehicles": [
                    {"id": "tesla", "vt1_model": "vehicle.tesla.model3",
                     "vt2_model": "vehicle.tesla.model3"},
                    {"id": "audi", "vt1_model": "vehicle.audi.tt",
                     "vt2_model": "vehicle.audi.tt"},
                ],
            }
            plan, manifest_path, entries = expand(
                config, source_dir, output_dir)
            self.assertEqual(plan["scenario_count"], 4)
            self.assertEqual(len(entries), 4)
            self.assertTrue(manifest_path.is_file())
            for path in output_dir.glob("scenario_2b_*.json"):
                document = json.loads(path.read_text(encoding="utf-8"))
                validate_roundabout_config(
                    document["FakeTown"]["route_01"][0],
                    require_reproducibility=False)


if __name__ == "__main__":
    unittest.main()
