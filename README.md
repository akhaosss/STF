# STF CARLA 场景编辑器与 ADS 测试运行器

本仓库使用 CARLA 生成、运行并记录自动驾驶测试场景。当前主流程基线为 **Ubuntu、Python 3.10、CARLA 0.9.16**，核心入口是：

- `waypoints.py`：交互式场景编辑器；
- `run.py`：场景运行与结果记录；
- `scripts/`：环境检查及 YAML 驱动的一键启动脚本；
- `TCP/`：仓库内集成的 TCP 模型及其上游依赖代码。

## 新用户从这里开始

1. 按 [环境安装与验证](docs/environment_setup.md) 创建或检查 `carla0916` 环境。
2. 执行环境自检：

   ```bash
   ./scripts/check_environment.sh
   ```

3. 根据目标场景进入专项文档：

   - 环形路口 2.b：[直接运行已有场景](docs/scenarios/2b_roundabout/run_existing.md)、[场景定义与对应关系](docs/scenarios/2b_roundabout/README.md)、[编辑与扩展](docs/scenarios/2b_roundabout/startup.md)、[参数、证据与结果目录](docs/scenarios/2b_roundabout/results_and_parameters.md)；
   - 机动车信号灯 1.d：[场景说明](docs/scenarios/1d_motor_vehicle_signal/README.md)；
   - 其他通用场景：[编辑器与运行器手册](docs/README.md)。

仓库已经发布可直接运行的环形路口场景定义，位于`save_scenarios/2b/definitions/`。启动CARLA并核对[统一配置](config/roundabout_2b.yaml)后，可以直接运行参考控制器示例：

```bash
./scripts/run_roundabout_behavior.sh
```

只有修改路线、车辆布置或拓扑时才启动编辑器：

```bash
./scripts/start_roundabout_editor.sh
```

仓库参考控制器和TCP均为ADS接入示例，不要求使用者依次完成双ADS实验。具体ADS、重复次数和正式判定方式由测试计划确定。

## 文档地图

### 当前主项目文档

| 阅读顺序 | 文档 | 用途 | 适用版本/状态 |
|---|---|---|---|
| 1 | [环境安装与验证](docs/environment_setup.md) | 从零创建 Conda 环境、安装 CARLA Python API、检查 FFmpeg/CUDA | 当前主流程，CARLA 0.9.16 |
| 2 | [直接运行已有2.b场景](docs/scenarios/2b_roundabout/run_existing.md) | 使用随仓库发布的JSON，不打开编辑器即可运行 | 当前2.b最短入口 |
| 3 | [环岛场景定义与对应关系](docs/scenarios/2b_roundabout/README.md) | 国标场景、仓库场景、逐项映射、判定边界 | 当前2.b设计说明 |
| 4 | [环岛编辑与扩展](docs/scenarios/2b_roundabout/startup.md) | 修改路线、天气和车型 | 需要生成新场景时阅读 |
| 5 | [环岛参数、证据与结果目录](docs/scenarios/2b_roundabout/results_and_parameters.md) | 参数来源/单位、国标对应、20 Hz遥测和批次目录 | 当前2.b数据字典 |
| 6 | [机动车信号灯 1.d](docs/scenarios/1d_motor_vehicle_signal/README.md) | 路线矩阵、信号灯时序、运行和结果 | 当前1.d专项说明 |
| 7 | [通用编辑器与运行器](docs/README.md) | 非专项场景的旧通用流程 | 2.b/1.d用户无需阅读 |

### 历史或辅助项目文档

这些文件保留背景信息，但不能覆盖上表中的当前安装和专项说明：

| 文档 | 关系与使用方式 |
|---|---|
| [waypoints操作说明.md](docs/waypoints操作说明.md) | 旧版通用快捷键和碰撞增强说明；2.b/1.d 应以专项文档为准 |
| [waypoints.md](waypoints.md) | 更早期的编辑器操作记录，部分按键和输出格式已经变化，仅用于追溯 |
| [机动车信号灯 ScenarioRunner 实验记录](docs/james.md) | TCP 上游 ScenarioRunner/旧 CARLA 0.9.10.1 实验记录，不等同于当前根目录 `run.py` 的 1.d 流程 |
| [good_env.txt](good_env.txt) | 某台机器包含 ROS、Autoware、CUDA的完整包快照，不是最小依赖清单 |
| [version.txt](version.txt) | 碰撞增强功能的历史使用备注，不是项目版本声明 |

### TCP、Leaderboard 与 ScenarioRunner 上游文档

`TCP/` 是集成进仓库的上游子项目。其文档使用 **CARLA 0.9.10.1/Python 3.7** 基线，只有运行上游训练、Leaderboard或ScenarioRunner时才按其说明单独建环境；不要用它覆盖当前主流程的 `carla0916`。

- TCP模型：[TCP README](TCP/README.md)、[旧环境定义](TCP/environment.yml)；
- Leaderboard：[README](TCP/leaderboard/README.md)、[依赖清单](TCP/leaderboard/requirements.txt)、[CHANGELOG](TCP/leaderboard/CHANGELOG.md)；
- ScenarioRunner入口：[README](TCP/scenario_runner/README.md)、[文档索引](TCP/scenario_runner/Docs/index.md)；
- 安装与入门：[获取 ScenarioRunner](TCP/scenario_runner/Docs/getting_scenariorunner.md)、[运行依赖](TCP/scenario_runner/requirements.txt)、[文档构建依赖](TCP/scenario_runner/Docs/requirements.txt)、[Getting Started](TCP/scenario_runner/Docs/getting_started.md)、[FAQ](TCP/scenario_runner/Docs/FAQ.md)；
- 场景开发与格式：[创建场景](TCP/scenario_runner/Docs/creating_new_scenario.md)、[支持场景列表](TCP/scenario_runner/Docs/list_of_scenarios.md)、[OpenSCENARIO](TCP/scenario_runner/Docs/openscenario_support.md)；
- 评测与集成：[Agent评测](TCP/scenario_runner/Docs/agent_evaluation.md)、[ROS Agent](TCP/scenario_runner/Docs/ros_agent.md)、[Metrics](TCP/scenario_runner/Docs/metrics_module.md)；
- 上游协作资料：[CONTRIBUTING](TCP/scenario_runner/Docs/CONTRIBUTING.md)、[Coding Standard](TCP/scenario_runner/Docs/coding_standard.md)、[Code of Conduct](TCP/scenario_runner/Docs/CODE_OF_CONDUCT.md)、[CHANGELOG](TCP/scenario_runner/Docs/CHANGELOG.md)。

### 专用工具文档

- [Tripo StaticMesh 距离场崩溃处理](tools/tripo_distance_field_fix/README.md)：仅在 CARLA UE4 自定义资产触发距离场崩溃时使用，与日常场景编辑无关。

## 目录关系

```text
环境准备
   └── docs/environment_setup.md
            │
            ├── 通用场景 ── docs/README.md
            ├── 1.d信号灯 ─ docs/scenarios/1d_motor_vehicle_signal/README.md
            └── 2.b环岛 ─── docs/scenarios/2b_roundabout/run_existing.md
                              ├── save_scenarios/2b/definitions/
                              ├── docs/scenarios/2b_roundabout/README.md
                              ├── config/roundabout_2b.yaml
                              └── docs/scenarios/2b_roundabout/startup.md

第三方/旧版独立流程
   └── TCP/README.md
        ├── TCP/leaderboard/
        └── TCP/scenario_runner/
```

如果当前文档与历史/上游文档冲突，根目录主流程以 [环境安装与验证](docs/environment_setup.md) 和对应场景专项文档为准。
