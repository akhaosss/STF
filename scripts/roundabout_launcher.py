#!/usr/bin/env python3
"""YAML-driven launcher for the GB/T 41798 2.b editor and controller examples."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from roundabout_2b import (  # noqa: E402
    generate_roundabout_trial_matrix,
    roundabout_condition_payload,
    validate_roundabout_config,
    validate_roundabout_matrix,
)
from weather_catalog import (  # noqa: E402
    WEATHER_PRESET_ORDER,
    build_weather_catalog,
)


DEFAULT_CONFIG = REPO_ROOT / "config" / "roundabout_2b.yaml"
WEATHER_PRESETS = set(WEATHER_PRESET_ORDER)


class ConfigError(ValueError):
    """Raised when the unified roundabout configuration is incomplete."""


def _mapping(value, path):
    if not isinstance(value, dict):
        raise ConfigError("{} 必须是 YAML 对象".format(path))
    return value


def _text(value, path, allow_empty=False):
    if not isinstance(value, str):
        raise ConfigError("{} 必须是字符串".format(path))
    value = value.strip()
    if not value and not allow_empty:
        raise ConfigError("{} 不能为空".format(path))
    return value


def _integer(value, path, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("{} 必须是整数".format(path))
    if minimum is not None and value < minimum:
        raise ConfigError("{} 必须不小于 {}".format(path, minimum))
    if maximum is not None and value > maximum:
        raise ConfigError("{} 必须不大于 {}".format(path, maximum))
    return value


def _optional_positive_number(value, path):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("{} 必须是正数或 null".format(path))
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ConfigError("{} 必须大于 0".format(path))
    return result


def _nonnegative_number(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("{} 必须是非负数".format(path))
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ConfigError("{} 必须不小于 0".format(path))
    return result


def _bool(value, path):
    if not isinstance(value, bool):
        raise ConfigError("{} 必须是 true 或 false".format(path))
    return value


def _identifier(value, path):
    value = _text(value, path)
    if not all(character.isalnum() or character in "_-" for character in value):
        raise ConfigError("{} 只能包含字母、数字、下划线和连字符".format(path))
    return value


def _roundabout_variants(editor):
    weather_items = editor.get("weather_profiles")
    vehicle_items = editor.get("vehicle_profiles")
    if not isinstance(weather_items, list) or not weather_items:
        raise ConfigError("editor.weather_profiles 必须是非空列表")
    if not isinstance(vehicle_items, list) or not vehicle_items:
        raise ConfigError("editor.vehicle_profiles 必须是非空列表")

    weather_profiles = []
    weather_ids = set()
    weather_catalog = build_weather_catalog()

    def append_weather(profile):
        profile_id = profile["id"]
        if profile_id in weather_ids:
            raise ConfigError("天气配置 id 重复：{}".format(profile_id))
        weather_ids.add(profile_id)
        weather_profiles.append(profile)

    for index, raw in enumerate(weather_items):
        path = "editor.weather_profiles[{}]".format(index)
        item = _mapping(raw, path)
        profile_id = _identifier(item.get("id"), path + ".id")
        if "parameters" in item:
            parameters = _mapping(item.get("parameters"), path + ".parameters")
            if not parameters:
                raise ConfigError(path + ".parameters 不能为空")
            append_weather({"id": profile_id, "parameters": parameters})
            continue
        preset = _text(item.get("preset"), path + ".preset")
        if preset == "all":
            for built_in in WEATHER_PRESET_ORDER:
                for level in range(1, 9):
                    append_weather({
                        "id": "{}_{:02d}".format(built_in, level),
                        "preset": built_in,
                        "level": level,
                        "parameters": weather_catalog[built_in][level - 1],
                    })
            continue
        if preset not in WEATHER_PRESETS:
            raise ConfigError(
                "{} 不支持；可选值：all, {}".format(
                    path + ".preset", ", ".join(WEATHER_PRESET_ORDER)))
        level = _integer(item.get("level"), path + ".level", 1, 8)
        append_weather({
            "id": profile_id, "preset": preset, "level": level,
            "parameters": weather_catalog[preset][level - 1],
        })

    vehicle_profiles = []
    vehicle_ids = set()
    for index, raw in enumerate(vehicle_items):
        path = "editor.vehicle_profiles[{}]".format(index)
        item = _mapping(raw, path)
        profile_id = _identifier(item.get("id"), path + ".id")
        if profile_id in vehicle_ids:
            raise ConfigError("车型配置 id 重复：{}".format(profile_id))
        vehicle_ids.add(profile_id)
        vt1_model = _text(item.get("vt1_model"), path + ".vt1_model")
        vt2_model = _text(item.get("vt2_model"), path + ".vt2_model")
        if not vt1_model.startswith("vehicle.") or not vt2_model.startswith("vehicle."):
            raise ConfigError("{} 的 VT1/VT2 必须使用 vehicle.* blueprint".format(path))
        vehicle_profiles.append({
            "id": profile_id,
            "vt1_model": vt1_model,
            "vt2_model": vt2_model,
        })
    return {"weather": weather_profiles, "vehicles": vehicle_profiles}


def _repo_path(value, path, allow_empty=False):
    text = _text(value, path, allow_empty=allow_empty)
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate.resolve()


def load_config(path=DEFAULT_CONFIG):
    config_path = Path(path).resolve()
    try:
        raw_bytes = config_path.read_bytes()
    except OSError as exc:
        raise ConfigError("无法读取配置 {}：{}".format(config_path, exc)) from exc
    try:
        raw = yaml.safe_load(raw_bytes) or {}
    except yaml.YAMLError as exc:
        raise ConfigError("YAML 解析失败：{}".format(exc)) from exc
    root = _mapping(raw, "配置根节点")
    if root.get("schema_version") != 1:
        raise ConfigError("schema_version 必须为 1")

    environment = _mapping(root.get("environment"), "environment")
    connection = _mapping(root.get("connection"), "connection")
    editor = _mapping(root.get("editor"), "editor")
    conflict_sync = _mapping(
        editor.get("conflict_sync", {}), "editor.conflict_sync")
    runner = _mapping(root.get("runner"), "runner")
    screening = _mapping(runner.get("screening", {}), "runner.screening")
    ads = _mapping(root.get("ads"), "ads")
    behavior = _mapping(ads.get("behavior"), "ads.behavior")
    tcp = _mapping(ads.get("tcp"), "ads.tcp")

    collision_value = runner.get("collision_config")
    if collision_value is None:
        collision_path = None
    else:
        collision_path = _repo_path(
            collision_value, "runner.collision_config", allow_empty=True)

    conflict_headway_s = _optional_positive_number(
        conflict_sync.get("target_headway_s", 2.5),
        "editor.conflict_sync.target_headway_s")
    conflict_tolerance_s = _nonnegative_number(
        conflict_sync.get("tolerance_s", 1.5),
        "editor.conflict_sync.tolerance_s")
    if conflict_tolerance_s > conflict_headway_s:
        raise ConfigError(
            "editor.conflict_sync.tolerance_s 不能大于 target_headway_s")

    return {
        "config_path": config_path,
        "config_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "conda_env": _text(
            environment.get("conda_env", ""),
            "environment.conda_env", allow_empty=True),
        "carla_root": _repo_path(
            environment.get("carla_root", ""),
            "environment.carla_root", allow_empty=True),
        "host": _text(connection.get("host"), "connection.host"),
        "port": _integer(connection.get("port"), "connection.port", 1, 65535),
        "wait_timeout_s": _integer(
            connection.get("wait_timeout_s"), "connection.wait_timeout_s", 0),
        "expected_map": _text(
            connection.get("expected_map", ""),
            "connection.expected_map", allow_empty=True),
        "save_dir": _repo_path(editor.get("save_dir"), "editor.save_dir"),
        "seed": _integer(editor.get("seed"), "editor.seed"),
        "speed_limit_kmh": _optional_positive_number(
            editor.get("speed_limit_kmh"), "editor.speed_limit_kmh"),
        "roundabout_variants": _roundabout_variants(editor),
        "conflict_headway_s": conflict_headway_s,
        "conflict_tolerance_s": conflict_tolerance_s,
        "vt1_post_exit_clearance_distance_m": _optional_positive_number(
            editor.get("vt1_post_exit_clearance_distance_m", 25.0),
            "editor.vt1_post_exit_clearance_distance_m"),
        "input_dir": _repo_path(runner.get("input_dir"), "runner.input_dir"),
        "route_id": _text(runner.get("route_id"), "runner.route_id"),
        "max_invalid_retries": _integer(
            runner.get("max_invalid_retries"),
            "runner.max_invalid_retries", 0),
        "formal_repetitions": _integer(
            runner.get("repetitions", 3), "runner.repetitions", 3, 3),
        "experiment_root": _repo_path(
            runner.get("experiment_root"), "runner.experiment_root"),
        "screening_root": _repo_path(
            screening.get("output_root", "./runs/roundabout_screening"),
            "runner.screening.output_root"),
        "screening_max_invalid_retries": _integer(
            screening.get("max_invalid_retries", 0),
            "runner.screening.max_invalid_retries", 0),
        "headless": _bool(
            runner.get("headless", True), "runner.headless"),
        "collision_config": collision_path,
        "behavior_description": _text(
            behavior.get("description"), "ads.behavior.description"),
        "tcp_model_path": _repo_path(
            tcp.get("model_path", ""), "ads.tcp.model_path", allow_empty=True),
        "tcp_require_cuda": _bool(
            tcp.get("require_cuda"), "ads.tcp.require_cuda"),
    }


def configure_carla_pythonapi(config):
    carla_root = config["carla_root"]
    if carla_root is None:
        env_root = os.environ.get("CARLA_UE4_ROOT") \
            or os.environ.get("CARLA_0916_ROOT")
        if env_root:
            carla_root = Path(env_root).resolve()
    if carla_root is None:
        raise ConfigError(
            "无法确定 CARLA 根目录；请设置环境变量或填写 environment.carla_root")
    agents_dir = carla_root / "PythonAPI" / "carla"
    if not (agents_dir / "agents" / "navigation").is_dir():
        raise ConfigError(
            "CARLA PythonAPI 不完整：{}".format(agents_dir / "agents" / "navigation"))
    agents_text = str(agents_dir)
    if agents_text not in sys.path:
        sys.path.insert(0, agents_text)
    child_env = os.environ.copy()
    existing = child_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = agents_text + ((os.pathsep + existing) if existing else "")
    return carla_root, child_env


def wait_for_carla(config):
    import carla

    started_at = time.monotonic()
    deadline = started_at + config["wait_timeout_s"]
    next_progress_at = started_at
    last_error = None
    print(
        "正在连接 CARLA {}:{}（最长等待 {} 秒）……".format(
            config["host"], config["port"], config["wait_timeout_s"]),
        flush=True)
    while True:
        try:
            client = carla.Client(config["host"], config["port"])
            client.set_timeout(1.0)
            world = client.get_world()
            map_full_name = str(world.get_map().name).rstrip("/")
            map_name = map_full_name.rsplit("/", 1)[-1]
            expected = config["expected_map"].rstrip("/").rsplit("/", 1)[-1]
            if expected and map_name.lower() != expected.lower():
                raise ConfigError(
                    "地图不一致：CARLA 当前为 {!r}，配置期望 {!r}".format(
                        map_name, expected))
            return {
                "client": client,
                "world": world,
                "map_name": map_name,
                "map_full_name": map_full_name,
                "client_version": client.get_client_version(),
                "server_version": client.get_server_version(),
            }
        except ConfigError:
            raise
        except RuntimeError as exc:
            last_error = exc
            now = time.monotonic()
            if now >= deadline:
                raise ConfigError(
                    "未检测到可响应的 CARLA Server（{}:{}）。请先启动CARLA并确认"
                    "-carla-port与YAML一致；底层错误：{}".format(
                        config["host"], config["port"], last_error)) from exc
            if now >= next_progress_at:
                elapsed = int(max(0.0, now - started_at))
                print(
                    "  CARLA尚未就绪，已等待 {} 秒；启动器会继续重试……".format(
                        elapsed),
                    flush=True)
                next_progress_at = now + 5.0
            time.sleep(1.0)


def print_connection(info):
    print("CARLA 已连接：")
    print("  client: {}".format(info["client_version"]))
    print("  server: {}".format(info["server_version"]))
    print("  map:    {}".format(info["map_name"]))


def editor_command(config, map_name):
    command = [
        sys.executable,
        str(REPO_ROOT / "waypoints.py"),
        "--host", config["host"],
        "--port", str(config["port"]),
        "--name", map_name,
        "--scenario", "2b",
        "--seed", str(config["seed"]),
        "--save_dir", str(config["save_dir"]),
        "--roundabout_variants_json",
        json.dumps(config["roundabout_variants"], ensure_ascii=False),
        "--roundabout_conflict_headway_s", str(config["conflict_headway_s"]),
        "--roundabout_conflict_tolerance_s", str(config["conflict_tolerance_s"]),
        "--roundabout_vt1_post_exit_clearance_distance_m",
        str(config["vt1_post_exit_clearance_distance_m"]),
    ]
    if config["speed_limit_kmh"] is not None:
        command.extend([
            "--roundabout_speed_limit_kmh",
            str(config["speed_limit_kmh"]),
        ])
    return command


def run_command(
        config, map_name, model, input_dir=None, screening=False,
        batch_dir=None, batch_id=None):
    output_root = config["screening_root"] if screening \
        else config["experiment_root"]
    video_dir = (batch_dir or output_root) / model
    command = [
        sys.executable,
        str(REPO_ROOT / "run.py"),
        "--host", config["host"],
        "--port", str(config["port"]),
        "--input_dir", str(input_dir or config["input_dir"]),
        "--town", map_name,
        "--route_id", config["route_id"],
        "--scenario", "2b",
        "--model", model,
        "--max_invalid_retries", str(
            config["screening_max_invalid_retries"] if screening
            else config["max_invalid_retries"]),
        "--video_dir", str(video_dir),
    ]
    if batch_id:
        command.extend([
            "--batch_id", str(batch_id),
            "--launcher_config_path", str(config["config_path"]),
            "--launcher_config_sha256", str(config["config_sha256"]),
        ])
    if screening:
        command.append("--screening")
    # Behavior is an unattended reference/screening controller and must never
    # create a desktop Pygame window.  Keep the explicit flag in the generated
    # command as well as the run.py fallback so manifests and shell logs show
    # the effective mode.
    if config["headless"] or model == "behavior":
        command.append("--headless")
    if config["collision_config"] is not None:
        command.extend([
            "--collision_config", str(config["collision_config"]),
        ])
    if model == "tcp":
        command.extend(["--model_path", str(config["tcp_model_path"])])
    return command


def _write_manifest(path, manifest):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    os.replace(temporary, path)


def launch_editor(config, child_env):
    info = wait_for_carla(config)
    print_connection(info)
    config["save_dir"].mkdir(parents=True, exist_ok=True)
    command = editor_command(config, info["map_name"])
    print("启动 2.b 编辑器，输出目录：{}".format(config["save_dir"]))
    return subprocess.call(command, cwd=REPO_ROOT, env=child_env)


def validate_formal_run(config, models=("behavior", "tcp")):
    if not config["input_dir"].is_dir():
        raise ConfigError(
            "场景目录不存在：{}；请检查runner.input_dir，发布数据默认位于"
            "save_scenarios/2b/definitions".format(config["input_dir"]))
    scenario_files = sorted(config["input_dir"].glob("scenario_2b_*.json"))
    if not scenario_files:
        raise ConfigError(
            "没有找到scenario_2b_*.json；请检查runner.input_dir或恢复仓库发布的"
            "save_scenarios/2b/definitions数据")
    if "tcp" in models:
        if config["tcp_model_path"] is None:
            raise ConfigError("请在 YAML 的 ads.tcp.model_path 填写 TCP checkpoint")
        if not config["tcp_model_path"].is_file():
            raise ConfigError("TCP checkpoint 不存在：{}".format(
                config["tcp_model_path"]))
    if config["collision_config"] is not None \
            and not config["collision_config"].is_file():
        raise ConfigError("碰撞配置不存在：{}".format(config["collision_config"]))
    if "tcp" in models and config["tcp_require_cuda"]:
        import torch
        if not torch.cuda.is_available():
            raise ConfigError("ads.tcp.require_cuda=true，但当前环境没有可用 CUDA")
    return scenario_files


def _scenario_config(document, map_name, route_id):
    if not isinstance(document, dict):
        raise ConfigError("场景JSON根节点必须是对象")
    map_key = next(
        (key for key in document
         if str(key).rsplit("/", 1)[-1].lower() == map_name.lower()), None)
    if map_key is None:
        raise ConfigError("场景JSON不包含当前地图 {}".format(map_name))
    routes = document.get(map_key)
    if not isinstance(routes, dict) or route_id not in routes:
        raise ConfigError("场景JSON不包含路线键 {}".format(route_id))
    configs = routes[route_id]
    if not isinstance(configs, list) or len(configs) != 1:
        raise ConfigError("每个2.b场景JSON必须恰好包含一个场景配置")
    return map_key, configs[0]


def prepare_formal_scenarios(
        config, scenario_files, map_name, prepared_root=None):
    """Expand standalone scene definitions into three formal repetitions."""
    documents = []
    has_reproducibility = []
    for path in scenario_files:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            map_key, scenario = _scenario_config(
                document, map_name, config["route_id"])
        except (OSError, ValueError, ConfigError) as exc:
            raise ConfigError("无法读取场景 {}：{}".format(path, exc)) from exc
        documents.append((path, document, map_key, scenario))
        has_reproducibility.append(isinstance(
            scenario.get("roundabout_test", {}).get("reproducibility"), dict))

    if all(has_reproducibility):
        try:
            validate_roundabout_matrix([item[3] for item in documents])
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        return config["input_dir"], scenario_files
    if any(has_reproducibility):
        raise ConfigError("输入目录混合了场景定义和旧版三次试验文件，请分目录保存")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    prepared_dir = (prepared_root or (
        config["experiment_root"] / "prepared_scenarios")) / stamp
    prepared_dir.mkdir(parents=True, exist_ok=False)
    prepared_paths = []
    prepared_configs = []
    for source_index, (source_path, _, map_key, source_config) in enumerate(
            documents, start=1):
        try:
            validate_roundabout_config(
                source_config, require_reproducibility=False)
            condition = roundabout_condition_payload(source_config)
            trials, _, _ = generate_roundabout_trial_matrix(
                config["seed"], condition,
                repetitions=config["formal_repetitions"])
        except ValueError as exc:
            raise ConfigError("场景定义 {} 无效：{}".format(source_path, exc)) from exc
        for trial in trials:
            scenario = copy.deepcopy(source_config)
            base_name = str(scenario.get("name") or source_path.stem)
            scenario["name"] = "{}_trial_{:02d}".format(
                base_name, trial["trial_index"])
            metadata = dict(trial)
            metadata["topology_hash"] = scenario["roundabout_test"].get(
                "topology_hash")
            metadata["source_scenario"] = source_path.name
            scenario["roundabout_test"]["reproducibility"] = metadata
            try:
                validate_roundabout_config(scenario)
            except ValueError as exc:
                raise ConfigError(
                    "正式重复场景展开失败 {}：{}".format(source_path, exc)) from exc
            document = {map_key: {config["route_id"]: [scenario]}}
            output = prepared_dir / "scenario_2b_{:04d}_{}_trial_{:02d}.json".format(
                source_index, metadata["matrix_id"][:8], metadata["trial_index"])
            output.write_text(
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
            prepared_paths.append(output)
            prepared_configs.append(scenario)
    try:
        validate_roundabout_matrix(prepared_configs)
    except ValueError as exc:
        raise ConfigError("正式试验展开后的矩阵无效：{}".format(exc)) from exc
    return prepared_dir, prepared_paths


def launch_formal_experiments(config, child_env, models=("behavior", "tcp")):
    models = tuple(models)
    if not models or any(model not in ("behavior", "tcp") for model in models):
        raise ConfigError("ADS列表只能包含 behavior 或 tcp")
    scenario_files = validate_formal_run(config, models=models)
    info = wait_for_carla(config)
    print_connection(info)
    config["experiment_root"].mkdir(parents=True, exist_ok=True)
    batch_id = "batch_{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
    batch_dir = config["experiment_root"] / batch_id
    batch_dir.mkdir(parents=True, exist_ok=False)
    formal_input_dir, formal_scenario_files = prepare_formal_scenarios(
        config, scenario_files, info["map_name"],
        prepared_root=batch_dir / "prepared_scenarios")
    manifest_path = batch_dir / "roundabout_experiment_manifest.json"
    manifest = {
        "schema_version": 1,
        "batch_id": batch_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config["config_path"]),
        "config_sha256": config["config_sha256"],
        "map_name": info["map_name"],
        "carla_client_version": info["client_version"],
        "carla_server_version": info["server_version"],
        "source_scenario_files": [str(path) for path in scenario_files],
        "formal_scenario_files": [str(path) for path in formal_scenario_files],
        "formal_input_dir": str(formal_input_dir),
        "repetitions_per_condition": config["formal_repetitions"],
        "ads_order": list(models),
        "ads": {},
    }
    _write_manifest(manifest_path, manifest)

    for index, model in enumerate(models, start=1):
        command = run_command(
            config, info["map_name"], model, input_dir=formal_input_dir,
            batch_dir=batch_dir, batch_id=batch_id)
        result_dir = batch_dir / model
        print("\n[{}/{}] 正式运行 {} ADS".format(index, len(models), model))
        print("结果目录：{}".format(result_dir))
        stage = {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "result_dir": str(result_dir),
        }
        manifest["ads"][model] = stage
        _write_manifest(manifest_path, manifest)
        try:
            subprocess.run(command, cwd=REPO_ROOT, env=child_env, check=True)
        except subprocess.CalledProcessError as exc:
            stage["status"] = "launcher_failed"
            stage["return_code"] = exc.returncode
            stage["finished_at"] = datetime.now(timezone.utc).isoformat()
            manifest["status"] = "incomplete"
            manifest["finished_at"] = stage["finished_at"]
            _write_manifest(manifest_path, manifest)
            raise ConfigError(
                "{} ADS 启动失败，返回码 {}；本次 ADS 实验未完成".format(
                    model, exc.returncode)) from exc
        stage["status"] = "completed"
        stage["return_code"] = 0
        stage["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_manifest(manifest_path, manifest)

    manifest["status"] = "completed"
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(manifest_path, manifest)
    print("\n{} ADS 正式实验已执行完成。".format("、".join(models)))
    print("实验清单：{}".format(manifest_path))
    return 0


def launch_behavior_screening(config, child_env):
    scenario_files = validate_formal_run(config, models=("behavior",))
    info = wait_for_carla(config)
    print_connection(info)
    config["screening_root"].mkdir(parents=True, exist_ok=True)
    batch_id = "screening_{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
    batch_dir = config["screening_root"] / batch_id
    batch_dir.mkdir(parents=True, exist_ok=False)
    result_dir = batch_dir / "behavior"
    print("\nBehavior场景筛选：每个定义运行1次，不生成三次正式重复。")
    print("场景定义数：{}".format(len(scenario_files)))
    print("结果目录：{}".format(result_dir))
    manifest_path = batch_dir / "roundabout_screening_manifest.json"
    manifest = {
        "schema_version": 1,
        "batch_id": batch_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config["config_path"]),
        "config_sha256": config["config_sha256"],
        "map_name": info["map_name"],
        "carla_client_version": info["client_version"],
        "carla_server_version": info["server_version"],
        "source_scenario_files": [str(path) for path in scenario_files],
        "result_dir": str(result_dir),
        "ads": "behavior",
        "repetitions_per_condition": 1,
    }
    _write_manifest(manifest_path, manifest)
    command = run_command(
        config, info["map_name"], "behavior",
        input_dir=config["input_dir"], screening=True,
        batch_dir=batch_dir, batch_id=batch_id)
    try:
        subprocess.run(command, cwd=REPO_ROOT, env=child_env, check=True)
    except subprocess.CalledProcessError as exc:
        manifest["status"] = "launcher_failed"
        manifest["return_code"] = exc.returncode
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_manifest(manifest_path, manifest)
        raise ConfigError(
            "Behavior筛选运行失败，返回码 {}".format(exc.returncode)) from exc
    manifest["status"] = "completed"
    manifest["return_code"] = 0
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(manifest_path, manifest)
    print("\nBehavior参考运行已完成；请使用视频和2b_result.csv/json查看结果。")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("editor", "run", "run-behavior", "run-tcp"))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        _, child_env = configure_carla_pythonapi(config)
        if args.mode == "editor":
            return launch_editor(config, child_env)
        if args.mode == "run-behavior":
            return launch_behavior_screening(config, child_env)
        if args.mode == "run-tcp":
            return launch_formal_experiments(config, child_env, models=("tcp",))
        return launch_formal_experiments(config, child_env)
    except ConfigError as exc:
        print("配置/启动错误：{}".format(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("用户中止。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
