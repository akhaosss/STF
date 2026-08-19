"""Pure helpers for the GB/T 41798-2022 1.d traffic-light scenario.

This module deliberately has no CARLA dependency so matrix generation and
result archival can be tested without a running simulator.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import os
import pickle
import random
from datetime import datetime, timezone


SCHEMA_VERSION = "gbt41798-1d-v1"
SIGNAL_CASES = ("keep_green", "turn_red")
MANEUVERS = ("straight", "left", "right")


def canonical_hash(value):
    """Return a stable SHA-256 hash for a JSON-compatible value."""
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path, chunk_size=1024 * 1024):
    """Hash an existing file without loading large model checkpoints in memory."""
    if not path or not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_signal_case_matrix(base_seed, route_key, repetitions=3):
    """Generate a deterministic matrix containing both signal cases.

    All sequences are equiprobable except the two invalid all-green/all-red
    sequences.  The derived seed is stored with the configuration so the exact
    choice can be reproduced independently of Python's randomized hash seed.
    """
    if repetitions < 2:
        raise ValueError("repetitions must be at least 2 to cover both cases")

    seed_material = "{}:{}:{}".format(base_seed, route_key, repetitions)
    derived_seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(derived_seed)
    valid_sequences = [
        sequence
        for sequence in itertools.product(SIGNAL_CASES, repeat=repetitions)
        if len(set(sequence)) == len(SIGNAL_CASES)
    ]
    sequence = rng.choice(valid_sequences)
    return list(sequence), derived_seed


def update_matrix_manifest(save_dir, entries, base_seed):
    """Merge generated scenario entries into a reproducibility manifest."""
    path = os.path.join(save_dir, "1d_matrix_manifest.json")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "base_seed": int(base_seed),
        "entries": [],
    }
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as stream:
            current = json.load(stream)
        if current.get("schema_version") == SCHEMA_VERSION:
            manifest = current
            manifest["base_seed"] = int(base_seed)

    by_file = {entry["file"]: entry for entry in manifest.get("entries", [])}
    for entry in entries:
        by_file[entry["file"]] = entry
    manifest["entries"] = [by_file[name] for name in sorted(by_file)]

    with open(path, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False, sort_keys=True)
    return path


def validate_signal_matrix(signal_configs, require_all_maneuvers=True):
    """Validate that every route fingerprint contains a complete 3-trial matrix."""
    groups = {}
    errors = []
    for config in signal_configs:
        reproducibility = config.get("reproducibility", {})
        fingerprint = reproducibility.get("route_fingerprint")
        if not fingerprint:
            errors.append("missing route_fingerprint")
            continue
        groups.setdefault(fingerprint, []).append(config)

    for fingerprint, group in groups.items():
        maneuvers = {item.get("maneuver") for item in group}
        cases = {item.get("signal_case") for item in group}
        indexes = {
            item.get("reproducibility", {}).get("trial_index") for item in group
        }
        seeds = {
            item.get("reproducibility", {}).get("matrix_seed") for item in group
        }
        if len(group) != 3:
            errors.append("route {} has {} trials, expected 3".format(fingerprint[:12], len(group)))
        if maneuvers - set(MANEUVERS) or len(maneuvers) != 1:
            errors.append("route {} has inconsistent maneuver values".format(fingerprint[:12]))
        if cases != set(SIGNAL_CASES):
            errors.append("route {} does not cover keep_green and turn_red".format(fingerprint[:12]))
        if indexes != {1, 2, 3}:
            errors.append("route {} trial indexes are not 1/2/3".format(fingerprint[:12]))
        if len(seeds) != 1 or None in seeds:
            errors.append("route {} has inconsistent matrix seeds".format(fingerprint[:12]))

    covered_maneuvers = {
        group[0].get("maneuver") for group in groups.values() if group
    }
    if require_all_maneuvers and covered_maneuvers != set(MANEUVERS):
        missing = sorted(set(MANEUVERS) - covered_maneuvers)
        errors.append("missing maneuver matrices: {}".format(", ".join(missing)))
    if not groups:
        errors.append("no 1.d matrix configurations found")
    if errors:
        raise ValueError("invalid 1.d test matrix: " + "; ".join(errors))
    return {
        "route_count": len(groups),
        "maneuvers": sorted(covered_maneuvers),
        "trial_count": sum(len(group) for group in groups.values()),
    }


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return str(value)


def _markdown_cell(value):
    if isinstance(value, (list, tuple)):
        value = "; ".join(str(item) for item in value)
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def load_existing_result_records(output_dir, scenario_code):
    """Load the durable ledger created by :func:`write_result_artifacts`."""
    path = os.path.join(output_dir, "{}_result.json".format(scenario_code))
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
        records = payload.get("records", []) if isinstance(payload, dict) else []
        return records if isinstance(records, list) else []
    except (OSError, ValueError):
        return []


def write_result_artifacts(records, output_dir, scenario_code, metadata=None):
    """Persist all accumulated results as Markdown, JSON, CSV and PKL.

    The function rewrites the complete snapshot after every scenario, making
    completed trials durable even if a later trial fails.
    """
    os.makedirs(output_dir, exist_ok=True)
    prefix = os.path.join(output_dir, "{}_result".format(scenario_code))
    safe_records = [_json_safe(record) for record in records]
    metadata = _json_safe(metadata or {})
    generated_at = datetime.now(timezone.utc).isoformat()

    payload = {
        "schema_version": SCHEMA_VERSION,
        "scenario_code": scenario_code,
        "generated_at_utc": generated_at,
        "metadata": metadata,
        "records": safe_records,
    }
    with open(prefix + ".json", "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, sort_keys=True)

    fieldnames = sorted({key for record in safe_records for key in record})
    with open(prefix + ".csv", "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for record in safe_records:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list)) else value
                for key, value in record.items()
            })

    with open(prefix + ".pkl", "wb") as stream:
        pickle.dump(safe_records, stream)

    pass_count = sum(record.get("pass") is True for record in safe_records)
    fail_count = sum(record.get("pass") is False for record in safe_records)
    matrix_groups = {}
    for record in safe_records:
        fingerprint = record.get("route_fingerprint")
        if fingerprint:
            matrix_groups.setdefault(fingerprint, []).append(record)
    complete_groups = sum(
        len(group) >= 3
        and {record.get("signal_case") for record in group} == set(SIGNAL_CASES)
        for group in matrix_groups.values()
    )

    columns = [
        "run_id", "scenario", "matrix_id", "maneuver", "trial_index", "signal_case",
        "matrix_seed", "trial_seed", "trigger_distance_m", "stop_gap_m",
        "restart_delay_s", "crossed_stop_line_on_red", "unjustified_stop",
        "collision", "route_complete", "pass", "failure_reasons",
    ]
    with open(prefix + ".md", "w", encoding="utf-8") as stream:
        stream.write("# GB/T 41798—2022 机动车信号灯（1.d）测试结果\n\n")
        stream.write("- 生成时间（UTC）：{}\n".format(generated_at))
        stream.write("- 已记录试验：{}\n".format(len(safe_records)))
        stream.write("- 通过：{}；失败：{}\n".format(pass_count, fail_count))
        stream.write("- 完整同路线矩阵：{} / {}\n".format(complete_groups, len(matrix_groups)))
        for key in sorted(metadata):
            stream.write("- {}：{}\n".format(key, _markdown_cell(metadata[key])))
        stream.write("\n## 逐次结果\n\n")
        stream.write("| " + " | ".join(columns) + " |\n")
        stream.write("| " + " | ".join(["---"] * len(columns)) + " |\n")
        for record in safe_records:
            stream.write("| " + " | ".join(
                _markdown_cell(record.get(column)) for column in columns
            ) + " |\n")

        stream.write("\n## 可复现性说明\n\n")
        stream.write(
            "每次试验保留基础种子、派生矩阵种子、路线指纹和输入配置哈希。"
            "使用相同地图、CARLA版本、被测模型及输入配置即可重放同一矩阵。\n"
        )

    return {
        "markdown": prefix + ".md",
        "json": prefix + ".json",
        "csv": prefix + ".csv",
        "pickle": prefix + ".pkl",
    }
