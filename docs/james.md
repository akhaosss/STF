# 机动车信号灯场景实验记录

> 历史/上游流程说明：本文使用TCP上游ScenarioRunner与CARLA 0.9.10.1，不是当前根目录 `run.py` 的1.d主流程。新用户请从仓库根目录 [README](../README.md) 选择正确文档。

## 目标

机动车信号灯对应地图 `1d`，需要运行以下三个 ScenarioRunner 场景：

| 场景 | 测试内容 | 示例配置 |
|---|---|---|
| `SignalizedJunctionRightTurn` | 有信号灯路口右转。Ego 车辆为红灯，横向直行车辆为绿灯。验证 Ego 是否在红灯前停车、避免与横向车辆碰撞。 | `TCP/scenario_runner/srunner/examples/SignalizedJunctionRightTurn.xml` |
| `SignalizedJunctionLeftTurn` | 有信号灯路口左转。Ego 车辆与对向直行车辆交互。验证 Ego 左转时是否正确让行并避免碰撞。 | `TCP/scenario_runner/srunner/examples/SignalizedJunctionLeftTurn.xml` |
| `OppositeVehicleRunningRedLight` | Ego 车辆为绿灯，横向车辆闯红灯。验证 Ego 是否能发现风险、减速或停车，并在路口清空后继续行驶。 | `TCP/scenario_runner/srunner/examples/RunningRedLight.xml` |

这些场景属于 `TCP/scenario_runner`，不属于根目录 `run.py` 当前支持的场景编号；应通过 `scenario_runner.py` 运行。

## 实验前准备

本仓库的 TCP README 要求 CARLA `0.9.10.1`；ScenarioRunner README 也要求 CARLA 与 ScenarioRunner 版本匹配。以下命令假设当前目录为仓库根目录。

```bash
conda activate TCP

export CARLA_ROOT=/path/to/CARLA_0.9.10.1
export PYTHONPATH="$PYTHONPATH:$CARLA_ROOT/PythonAPI"
export PYTHONPATH="$PYTHONPATH:$CARLA_ROOT/PythonAPI/carla"
export PYTHONPATH="$PYTHONPATH:$CARLA_ROOT/PythonAPI/carla/dist/carla-0.9.10-py3.7-linux-x86_64.egg"
export PYTHONPATH="$PYTHONPATH:$CARLA_ROOT/PythonAPI/carla/agents"
```

`carla-0.9.10-py3.7-linux-x86_64.egg` 必须按实际 Python 版本和平台替换。若尚未安装 ScenarioRunner 依赖，在 `TCP/scenario_runner` 目录执行：

```bash
pip install -r requirements.txt
```

启动 CARLA 服务端：

```bash
cd "$CARLA_ROOT"
./CarlaUE4.sh --world-port=2000 -opengl
```

## 运行场景

在另一个终端进入 ScenarioRunner 根目录。`--reloadWorld` 会依据 XML 中配置的 Town 自动重载地图。

```bash
cd /home/fsm/STF/SMap/STF/TCP/scenario_runner
```

### 1. 有信号灯路口右转

首个示例在 `Town03`：

```bash
python3 scenario_runner.py \
  --scenario SignalizedJunctionRightTurn_1 \
  --configFile srunner/examples/SignalizedJunctionRightTurn.xml \
  --reloadWorld
```

该 XML 还提供 `Town04` 的 `_2`、`_3` 和 `Town05` 的 `_4` 至 `_7` 实例。运行时应确认 Ego 面对红灯停车，横向车辆绿灯直行，且无闯灯和碰撞。

### 2. 有信号灯路口左转

首个示例在 `Town03`：

```bash
python3 scenario_runner.py \
  --scenario SignalizedJunctionLeftTurn_1 \
  --configFile srunner/examples/SignalizedJunctionLeftTurn.xml \
  --reloadWorld
```

该 XML 还提供 `Town04` 的 `_2`、`_3` 和 `Town05` 的 `_4` 至 `_6` 实例。运行时应确认 Ego 左转时没有抢占对向直行车路径，并且完成转弯前不发生碰撞。

### 3. 对向车辆闯红灯

首个示例在 `Town01`：

```bash
python3 scenario_runner.py \
  --scenario OppositeVehicleRunningRedLight_1 \
  --configFile srunner/examples/RunningRedLight.xml \
  --reloadWorld
```

该 XML 还提供 `Town02` 的 `_2` 以及 `Town03` 的 `_3` 至 `_5` 实例。运行时应确认 Ego 为绿灯，另一车辆为红灯但违法驶入路口；Ego 应避让、无碰撞，并在路口清空后继续前进。

## 控制 Ego 车辆

ScenarioRunner 文档建议另开终端，仍在 `TCP/scenario_runner` 目录运行：

```bash
python3 manual_control.py
```

手动控制适合先验证场景触发、车辆出生位置和信号灯状态。若要评测 TCP 模型，应使用其 Agent/Leaderboard 流程：在 `TCP/leaderboard/scripts/run_evaluation.sh` 配置 CARLA 路径、路线文件、场景文件和模型 checkpoint，再运行该脚本。该脚本的默认路线和场景文件不是本文件列出的三个 XML，不能直接替代上述单场景命令。

## 记录与判定

每次实验至少记录：场景实例名、Town、CARLA/ScenarioRunner 版本、Ego 控制器（手动或模型）、结果（成功、超时、碰撞）以及录像或日志路径。

重点观察：

- Ego 与其他车辆的信号灯状态是否符合场景设定。
- 是否出现碰撞、闯红灯、未让行、异常停车或超时。
- Ego 是否在风险解除后继续完成预期路线。
- 更换 XML 中不同 Town 实例后，行为是否稳定一致。

## 相关原始文档与配置

- `TCP/README.md`：TCP 的环境、CARLA 启动和评测流程。
- `TCP/scenario_runner/Docs/getting_started.md`：ScenarioRunner 环境变量、服务端启动、`--scenario`、`--reloadWorld` 与 `manual_control.py` 用法。
- `TCP/scenario_runner/Docs/list_of_scenarios.md`：三个场景的功能说明。
- `TCP/scenario_runner/srunner/examples/SignalizedJunctionRightTurn.xml`：右转场景的 Town 与车辆初始位姿。
- `TCP/scenario_runner/srunner/examples/SignalizedJunctionLeftTurn.xml`：左转场景的 Town 与车辆初始位姿。
- `TCP/scenario_runner/srunner/examples/RunningRedLight.xml`：闯红灯场景的 Town 与车辆初始位姿。
