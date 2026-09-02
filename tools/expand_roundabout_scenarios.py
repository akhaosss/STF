#!/usr/bin/env python3
"""Expand existing 2.b route JSONs into weather/target-vehicle scenarios."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from roundabout_2b import (  # noqa: E402
    canonical_hash,
    roundabout_condition_payload,
    validate_roundabout_config,
)
from scripts.roundabout_launcher import (  # noqa: E402
    DEFAULT_CONFIG,
    ConfigError,
    load_config,
)


def _read_document(path, route_id):
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError("无法读取 {}：{}".format(path, exc)) from exc
    matches = []
    if isinstance(document, dict):
        for map_key, routes in document.items():
            if isinstance(routes, dict) and route_id in routes:
                matches.append((map_key, routes[route_id]))
    if len(matches) != 1:
        raise ConfigError(
            "{} 必须恰好包含一个地图下的路线键 {}".format(path, route_id))
    map_key, scenarios = matches[0]
    if not isinstance(scenarios, list) or len(scenarios) != 1:
        raise ConfigError("{} 必须恰好包含一个2.b场景".format(path))
    return document, str(map_key), scenarios[0]


def _template_fingerprint(config):
    neutral = copy.deepcopy(config)
    neutral.pop("name", None)
    neutral["weather"] = {}
    test = neutral.get("roundabout_test", {})
    test.pop("reproducibility", None)
    test.pop("generation", None)
    actors = neutral.get("other_actors", {}).get("center", [])
    for actor in actors:
        if isinstance(actor, dict):
            role = str(actor.get("role") or actor.get("rolename") or "").lower()
            if role in ("vt1", "vt2"):
                actor["model"] = "vehicle.__target_model__"
    return canonical_hash(roundabout_condition_payload(neutral))


def discover_route_templates(input_dir, route_id):
    """Return unique route templates, collapsing legacy trial 1/2/3 files."""
    paths = sorted(Path(input_dir).glob("scenario_2b_*.json"))
    if not paths:
        raise ConfigError("{} 中没有 scenario_2b_*.json".format(input_dir))
    by_fingerprint = {}
    order = []
    for path in paths:
        _, map_key, config = _read_document(path, route_id)
        try:
            validate_roundabout_config(config, require_reproducibility=False)
        except ValueError as exc:
            raise ConfigError("基础场景 {} 无效：{}".format(path, exc)) from exc
        fingerprint = _template_fingerprint(config)
        if fingerprint not in by_fingerprint:
            base = copy.deepcopy(config)
            base.get("roundabout_test", {}).pop("reproducibility", None)
            base.get("roundabout_test", {}).pop("generation", None)
            by_fingerprint[fingerprint] = {
                "map_key": map_key,
                "config": base,
                "template_fingerprint": fingerprint,
                "source_files": [],
            }
            order.append(fingerprint)
        item = by_fingerprint[fingerprint]
        if item["map_key"] != map_key:
            raise ConfigError("相同路线指纹出现在不同地图中")
        item["source_files"].append(str(path.resolve()))
    return [by_fingerprint[fingerprint] for fingerprint in order]


def _role(actor):
    return str(actor.get("role") or actor.get("rolename") or "").lower()


def _expanded_name(variant, route_index):
    condition_id = "{}--{}".format(
        variant["weather"]["id"], variant["vehicle"]["id"])
    return "scenario_2b_route_{:04d}_{}".format(route_index, condition_id)


def build_expanded_config(template, variant, route_index, base_seed):
    scenario = copy.deepcopy(template["config"])
    condition_id = "{}--{}".format(
        variant["weather"]["id"], variant["vehicle"]["id"])
    name = _expanded_name(variant, route_index)
    scenario["name"] = name
    scenario["weather"] = copy.deepcopy(variant["weather"]["parameters"])
    actors = scenario.get("other_actors", {}).get("center", [])
    found = set()
    for actor in actors:
        role = _role(actor)
        if role == "vt1":
            actor["model"] = variant["vehicle"]["vt1_model"]
            found.add(role)
        elif role == "vt2":
            actor["model"] = variant["vehicle"]["vt2_model"]
            found.add(role)
    if found != {"vt1", "vt2"}:
        raise ConfigError("基础路线缺少唯一VT1/VT2目标车")
    condition_fingerprint = canonical_hash({
        "route_template_fingerprint": template["template_fingerprint"],
        "weather": scenario["weather"],
        "vt1_model": variant["vehicle"]["vt1_model"],
        "vt2_model": variant["vehicle"]["vt2_model"],
    })
    scenario["roundabout_test"]["generation"] = {
        "mode": "expanded_existing_route",
        "base_seed": int(base_seed),
        "condition_id": condition_id,
        "condition_fingerprint": condition_fingerprint,
        "route_template_fingerprint": template["template_fingerprint"],
        "weather_profile": variant["weather"]["id"],
        "vehicle_profile": variant["vehicle"]["id"],
        "source_files": list(template["source_files"]),
    }
    return name, scenario, condition_fingerprint


def _variants(config):
    configured = config["roundabout_variants"]
    return [
        {"weather": weather, "vehicle": vehicle}
        for weather in configured["weather"]
        for vehicle in configured["vehicles"]
    ]


def _compact_bytes(document):
    return (json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n").encode("utf-8")


def _atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".{}-".format(path.name), dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def expansion_plan(config, input_dir):
    templates = discover_route_templates(input_dir, config["route_id"])
    variants = _variants(config)
    estimate = 0
    for route_index, template in enumerate(templates):
        _, scenario, _ = build_expanded_config(
            template, variants[0], route_index, config["seed"])
        document = {template["map_key"]: {config["route_id"]: [scenario]}}
        estimate += len(_compact_bytes(document)) * len(variants)
    return {
        "templates": templates,
        "variants": variants,
        "route_count": len(templates),
        "weather_count": len(config["roundabout_variants"]["weather"]),
        "vehicle_count": len(config["roundabout_variants"]["vehicles"]),
        "scenario_count": len(templates) * len(variants),
        "estimated_bytes": estimate,
    }


def expand(config, input_dir, output_dir, overwrite=False, progress=None):
    plan = expansion_plan(config, input_dir)
    output_dir = Path(output_dir)
    expected_paths = []
    for route_index, template in enumerate(plan["templates"]):
        for variant in plan["variants"]:
            name = _expanded_name(variant, route_index)
            expected_paths.append(output_dir / (name + ".json"))
    collisions = [path for path in expected_paths if path.exists()]
    if collisions and not overwrite:
        raise ConfigError(
            "输出目录已有{}个同名场景；确认后使用--overwrite覆盖".format(
                len(collisions)))

    # Geometry, gates and actor placement are identical across variants, and
    # load_config has already validated every weather/model profile.  Validate
    # one representative per route instead of rescanning thousands of dense
    # route points for every weather/model combination.
    for route_index, template in enumerate(plan["templates"]):
        _, scenario, _ = build_expanded_config(
            template, plan["variants"][0], route_index, config["seed"])
        try:
            validate_roundabout_config(
                scenario, require_reproducibility=False)
        except ValueError as exc:
            raise ConfigError("扩展场景预检失败：{}".format(exc)) from exc

    entries = []
    generated = 0
    for route_index, template in enumerate(plan["templates"]):
        for variant in plan["variants"]:
            name, scenario, condition_fingerprint = build_expanded_config(
                template, variant, route_index, config["seed"])
            document = {
                template["map_key"]: {config["route_id"]: [scenario]}}
            payload = _compact_bytes(document)
            path = output_dir / (name + ".json")
            _atomic_write(path, payload)
            generated += 1
            entries.append({
                "file": path.name,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "route_index": route_index,
                "route_template_fingerprint": template["template_fingerprint"],
                "condition_fingerprint": condition_fingerprint,
                "weather_profile": variant["weather"]["id"],
                "vehicle_profile": variant["vehicle"]["id"],
            })
            if progress and (generated == 1 or generated == plan["scenario_count"]
                             or generated % 100 == 0):
                progress(generated, plan["scenario_count"], path)

    manifest = {
        "schema_version": 1,
        "generation_mode": "expanded_existing_routes",
        "input_dir": str(Path(input_dir).resolve()),
        "output_dir": str(output_dir.resolve()),
        "route_count": plan["route_count"],
        "weather_count": plan["weather_count"],
        "vehicle_count": plan["vehicle_count"],
        "scenario_count": plan["scenario_count"],
        "compact_json": True,
        "entries": entries,
    }
    manifest_path = output_dir / "2b_scenario_manifest.json"
    _atomic_write(manifest_path, json.dumps(
        manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
    return plan, manifest_path, entries


def _human_size(size):
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            return "{:.1f} {}".format(value, unit)
        value /= 1024.0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="用现有2.b路线批量生成天气×VT1/VT2车型场景")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input-dir", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        input_dir = Path(args.input_dir).resolve() if args.input_dir \
            else config["input_dir"]
        output_dir = Path(args.output_dir).resolve() if args.output_dir \
            else config["save_dir"]
        plan = expansion_plan(config, input_dir)
        print("识别独立路线：{}条".format(plan["route_count"]))
        print("天气：{}种；车型组合：{}组".format(
            plan["weather_count"], plan["vehicle_count"]))
        print("将生成：{}个场景".format(plan["scenario_count"]))
        print("预计紧凑JSON体积：约{}".format(
            _human_size(plan["estimated_bytes"])))
        print("输出目录：{}".format(output_dir))
        if args.dry_run:
            return 0

        def report(current, total, path):
            print("生成进度 {}/{}：{}".format(current, total, path.name), flush=True)

        _, manifest_path, entries = expand(
            config, input_dir, output_dir,
            overwrite=args.overwrite, progress=report)
        total_bytes = sum(entry["bytes"] for entry in entries)
        print("完成：{}个场景，实际体积{}".format(
            len(entries), _human_size(total_bytes)))
        print("清单：{}".format(manifest_path))
        return 0
    except ConfigError as exc:
        print("扩展失败：{}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
