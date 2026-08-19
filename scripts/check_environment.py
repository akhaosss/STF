#!/usr/bin/env python3
"""Check whether the current Conda environment can run the STF main workflow."""

from __future__ import annotations

import argparse
import importlib
from importlib import metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.roundabout_launcher import (  # noqa: E402
    ConfigError,
    configure_carla_pythonapi,
    load_config,
)


class Reporter:
    def __init__(self):
        self.failures = []
        self.warnings = []

    def ok(self, message):
        print("[ OK ] {}".format(message))

    def warn(self, message):
        self.warnings.append(message)
        print("[WARN] {}".format(message))

    def fail(self, message):
        self.failures.append(message)
        print("[FAIL] {}".format(message))


def _distribution_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def check_python_and_conda(config, report):
    if sys.version_info[:2] == (3, 10):
        report.ok("Python {}.{}.{}".format(*sys.version_info[:3]))
    else:
        report.fail(
            "当前Python为 {}.{}，主流程要求3.10".format(
                sys.version_info.major, sys.version_info.minor))
    active_env = os.environ.get("CONDA_DEFAULT_ENV", "")
    if active_env == config["conda_env"]:
        report.ok("Conda环境 {}".format(active_env))
    else:
        report.fail(
            "当前Conda环境为 {!r}，YAML配置为 {!r}".format(
                active_env, config["conda_env"]))


def check_dependencies(report):
    dependencies = (
        ("carla", "carla"),
        ("pygame", "pygame"),
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("imageio", "ImageIO"),
        ("imageio_ffmpeg", "imageio-ffmpeg"),
        ("yaml", "PyYAML"),
        ("PIL", "Pillow"),
        ("torch", "torch"),
        ("torchvision", "torchvision"),
    )
    modules = {}
    user_site = str(Path.home() / ".local" / "lib")
    for module_name, distribution_name in dependencies:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            report.fail(
                "无法导入 {}：{}: {}".format(
                    module_name, type(exc).__name__, exc))
            continue
        modules[module_name] = module
        version = _distribution_version(distribution_name) \
            or getattr(module, "__version__", "unknown")
        location = str(getattr(module, "__file__", "built-in"))
        report.ok("{} {} ({})".format(module_name, version, location))
        if location.startswith(user_site):
            report.warn("{} 来自 ~/.local，不是Conda环境自身".format(module_name))

    carla_version = _distribution_version("carla")
    if carla_version is not None and carla_version != "0.9.16":
        report.fail(
            "CARLA Python包版本为 {}，当前主流程要求0.9.16".format(
                carla_version))
    numpy_module = modules.get("numpy")
    if numpy_module is not None:
        try:
            numpy_major = int(numpy_module.__version__.split(".", 1)[0])
            if numpy_major >= 2:
                report.fail("当前代码基线要求NumPy 1.x，检测到 {}".format(
                    numpy_module.__version__))
        except (AttributeError, ValueError):
            report.warn("无法解析NumPy版本")
    return modules


def check_carla_pythonapi(config, report):
    try:
        carla_root, child_env = configure_carla_pythonapi(config)
    except ConfigError as exc:
        report.fail(str(exc))
        return None
    try:
        from agents.navigation.global_route_planner import GlobalRoutePlanner  # noqa: F401
    except Exception as exc:
        report.fail("无法导入agents.navigation.GlobalRoutePlanner：{}".format(exc))
        return None
    report.ok("CARLA根目录 {}".format(carla_root))
    report.ok("agents.navigation.GlobalRoutePlanner")
    return child_env


def check_video(modules, report):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        report.fail("找不到ffmpeg")
        return
    try:
        completed = subprocess.run(
            [ffmpeg, "-version"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        report.fail("ffmpeg无法运行：{}".format(exc))
        return
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ffmpeg
    if "--enable-libx264" in completed.stdout:
        report.ok("{}；libx264已启用".format(first_line))
    else:
        report.warn("{}；版本输出未证明libx264已启用".format(first_line))

    if "imageio" not in modules or "numpy" not in modules:
        return
    try:
        import imageio.v2 as imageio
        import numpy as np
        with tempfile.TemporaryDirectory(prefix="stf_env_check_") as directory:
            output = Path(directory) / "probe.mp4"
            writer = imageio.get_writer(str(output), fps=20, codec="libx264")
            writer.append_data(np.zeros((64, 64, 3), dtype=np.uint8))
            writer.close()
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError("输出文件为空")
        report.ok("ImageIO H.264 MP4实际写入")
    except Exception as exc:
        report.fail("ImageIO H.264写入失败：{}: {}".format(
            type(exc).__name__, exc))


def check_tcp(config, modules, report):
    checkpoint = config["tcp_model_path"]
    if checkpoint is None:
        report.fail("YAML ads.tcp.model_path尚未填写")
    elif not checkpoint.is_file():
        report.fail("TCP checkpoint不存在：{}".format(checkpoint))
    else:
        report.ok("TCP checkpoint {}".format(checkpoint))

    torch_module = modules.get("torch")
    if torch_module is None:
        return
    cuda_available = bool(torch_module.cuda.is_available())
    if cuda_available:
        report.ok("PyTorch CUDA可用：{}".format(torch_module.version.cuda))
    elif config["tcp_require_cuda"]:
        report.fail("YAML要求CUDA，但torch.cuda.is_available()为False")
    else:
        report.warn("CUDA不可用；YAML允许TCP使用CPU，实时性需要现场确认")


def check_repository_imports(child_env, report):
    if child_env is None:
        return
    previous = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = child_env.get("PYTHONPATH", "")
    try:
        for name in ("roundabout_2b", "waypoints", "scene", "run"):
            importlib.import_module(name)
        report.ok("仓库核心模块导入")
    except Exception as exc:
        report.fail("仓库核心模块导入失败：{}: {}".format(
            type(exc).__name__, exc))
    finally:
        if previous is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = previous


def check_server(config, modules, report):
    carla_module = modules.get("carla")
    if carla_module is None:
        return
    try:
        client = carla_module.Client(config["host"], config["port"])
        client.set_timeout(2.0)
        world = client.get_world()
        map_name = str(world.get_map().name).rstrip("/").rsplit("/", 1)[-1]
        report.ok(
            "CARLA Server {}:{}；client={} server={} map={}".format(
                config["host"], config["port"], client.get_client_version(),
                client.get_server_version(), map_name))
        expected = config["expected_map"].rstrip("/").rsplit("/", 1)[-1]
        if expected and expected.lower() != map_name.lower():
            report.fail("当前地图为 {!r}，YAML期望 {!r}".format(
                map_name, expected))
        elif not expected:
            report.warn("YAML connection.expected_map为空；正式实验建议固定地图名")
    except RuntimeError as exc:
        report.warn("CARLA Server当前不可连接：{}".format(exc))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default=str(REPO_ROOT / "config" / "roundabout_2b.yaml"))
    args = parser.parse_args(argv)
    report = Reporter()
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        report.fail("统一YAML无效：{}".format(exc))
        config = None
    if config is not None:
        check_python_and_conda(config, report)
        modules = check_dependencies(report)
        child_env = check_carla_pythonapi(config, report)
        check_video(modules, report)
        check_tcp(config, modules, report)
        check_repository_imports(child_env, report)
        check_server(config, modules, report)

    print("\n环境检查汇总：{} failure(s)，{} warning(s)".format(
        len(report.failures), len(report.warnings)))
    if report.failures:
        print("正式双ADS实验尚未就绪。")
        return 1
    print("环境满足当前主流程要求。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
