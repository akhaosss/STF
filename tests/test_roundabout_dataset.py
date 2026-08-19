import json
import unittest
from pathlib import Path

from roundabout_2b import canonical_hash, validate_roundabout_config
from scripts.roundabout_launcher import _scenario_config


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS = REPO_ROOT / "save_scenarios" / "2b" / "definitions"


class PublishedRoundaboutDatasetTest(unittest.TestCase):
    def test_manifest_covers_portable_valid_definitions(self):
        manifest = json.loads(
            (DEFINITIONS / "2b_scenario_manifest.json").read_text(
                encoding="utf-8"))
        entries = manifest["entries"]
        files = sorted(DEFINITIONS.glob("scenario_2b_*.json"))

        self.assertEqual(960, len(files))
        self.assertEqual(len(files), len(entries))
        entries_by_name = {entry["file"]: entry for entry in entries}
        self.assertEqual(len(entries), len(entries_by_name))

        for path in files:
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("/home/fsm/", raw, path.name)
            document = json.loads(raw)
            entry = entries_by_name[path.name]
            self.assertEqual(
                entry["config_sha256"], canonical_hash(document), path.name)
            _, config = _scenario_config(document, "STF-2-b", "route_01")
            validate_roundabout_config(
                config, require_reproducibility=False)


if __name__ == "__main__":
    unittest.main()
