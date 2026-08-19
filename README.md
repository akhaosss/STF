# STF GB/T 41798 2.b 环形路口场景分支

> 当前分支：`agent/gbt41798-roundabout-2b`

本分支在原STF/CARLA场景工具上增加GB/T 41798—2022第6.2.2条“环形路口”的场景定义、编辑、运行和证据记录能力，面向需要直接运行场景数据或接入自有ADS的使用者。

## 本分支提供什么

- 一条已审核的VUT/VT1/VT2环岛路线；
- 120种天气与8组VT1/VT2车型组合形成的960份可运行场景定义；
- VUT、VT1开放路线及VT2静止位置的可视化编辑器；
- 环岛入口、出口1/2/3、下游第1入口及目标车辆时序判定；
- 视频、20 Hz遥测、事件和判定摘要；
- 一个仓库参考控制器示例，以及供其他ADS复用的运行接口。

场景数据位于[`save_scenarios/2b/definitions/`](save_scenarios/2b/definitions/)。这些JSON已经包含路线、车辆、天气、车型、拓扑、门线和工程参数，**只运行现有场景时无需打开编辑器**。

## 最短使用流程

### 1. 准备环境

当前运行基线为Ubuntu、Python 3.10和CARLA 0.9.16。Conda环境名称由使用者自行确定，公共配置不绑定开发者机器上的环境名。完整安装方法见[环境安装与验证](docs/environment_setup.md)。

激活兼容环境后，在仓库根目录执行：

```bash
./scripts/check_environment.sh
```

### 2. 启动CARLA

启动CARLA 0.9.16 Server，并加载`STF-2-b`地图。发布的960份JSON与该地图的OpenDRIVE车道ID和坐标绑定；接入方必须准备相同地图，不能直接换成其他Town运行。

RPC地址、端口、地图名、输入目录和输出目录统一配置在[`config/roundabout_2b.yaml`](config/roundabout_2b.yaml)。

### 3. 先运行一个场景

默认输入目录包含960份JSON，首次联调不应直接运行全部文件。按[直接运行已有场景](docs/scenarios/2b_roundabout/run_existing.md#3-只运行部分场景)建立一个本地`runsets/smoke`目录，并在YAML中将`runner.input_dir`指向该目录，然后执行：

```bash
./scripts/run_roundabout_behavior.sh
```

该命令中的`behavior`调用仓库已有的`EgoRouteFollowScene.follow_route`，作为场景加载、车辆时序、证据记录和结果输出链路的参考控制器。

结果默认写入：

```text
runs/roundabout_screening/screening_<UTC时间>/behavior/
```

### 4. 根据用途继续

| 目标 | 下一步 |
|---|---|
| 直接运行发布场景 | 阅读[已有场景运行说明](docs/scenarios/2b_roundabout/run_existing.md) |
| 理解国标与JSON字段的对应关系 | 阅读[2.b场景定义](docs/scenarios/2b_roundabout/README.md) |
| 修改路线、车辆位置或拓扑 | 阅读[编辑与场景扩展](docs/scenarios/2b_roundabout/startup.md)，然后运行`./scripts/start_roundabout_editor.sh` |
| 查看参数来源、遥测和结果目录 | 阅读[参数、证据与结果目录](docs/scenarios/2b_roundabout/results_and_parameters.md) |
| 接入乙方自有ADS | 先用参考控制器打通流程，再按[使用其他ADS](docs/scenarios/2b_roundabout/run_existing.md#4-使用其他ads)适配控制接口 |

## 数据与执行约定

- 场景筛选按每个condition运行一次；重复评估按每个condition展开3次trial并聚合。
- 天气和VT1/VT2车型通过离线工具扩展；路线、车辆位置或拓扑改变时使用编辑器。
- `runs/`属于本地实验结果，不进入Git；`save_scenarios/2b/definitions/`是交付数据，必须保留在Git中。

## 仓库主要入口

- `waypoints.py`：交互式场景编辑器；
- `run.py`：场景运行与结果记录；
- `scripts/`：环境检查及YAML驱动的启动脚本；
- `roundabout_2b.py`：2.b配置校验、门线、重复试验和结果聚合。

## 文档地图

### 当前主项目文档

| 阅读顺序 | 文档 | 用途 | 适用版本/状态 |
|---|---|---|---|
| 1 | [环境安装与验证](docs/environment_setup.md) | 从零创建 Conda 环境、安装 CARLA Python API、检查 FFmpeg/CUDA | 当前主流程，CARLA 0.9.16 |
| 2 | [直接运行已有2.b场景](docs/scenarios/2b_roundabout/run_existing.md) | 使用随仓库发布的JSON，不打开编辑器即可运行 | 当前2.b最短入口 |
| 3 | [环岛场景定义与对应关系](docs/scenarios/2b_roundabout/README.md) | 国标场景、仓库场景、逐项映射、判定边界 | 当前2.b设计说明 |
| 4 | [环岛编辑与扩展](docs/scenarios/2b_roundabout/startup.md) | 修改路线、天气和车型 | 需要生成新场景时阅读 |
| 5 | [环岛参数、证据与结果目录](docs/scenarios/2b_roundabout/results_and_parameters.md) | 参数来源/单位、国标对应、20 Hz遥测和批次目录 | 当前2.b数据字典 |
| 6 | [通用编辑器与运行器](docs/README.md) | 非专项场景的旧通用流程 | 环岛2.b以专项文档为准 |

### 历史或辅助项目文档

这些文件保留背景信息，但不能覆盖上表中的当前安装和专项说明：

| 文档 | 关系与使用方式 |
|---|---|
| [waypoints操作说明.md](docs/waypoints操作说明.md) | 旧版通用快捷键和碰撞增强说明；环岛2.b以专项文档为准 |
| [waypoints.md](waypoints.md) | 更早期的编辑器操作记录，部分按键和输出格式已经变化，仅用于追溯 |
| [good_env.txt](good_env.txt) | 某台机器包含 ROS、Autoware、CUDA的完整包快照，不是最小依赖清单 |
| [version.txt](version.txt) | 碰撞增强功能的历史使用备注，不是项目版本声明 |

### TCP、Leaderboard 与 ScenarioRunner 上游文档

`TCP/` 是集成进仓库的上游子项目。其文档使用 **CARLA 0.9.10.1/Python 3.7** 基线，只有运行上游训练、Leaderboard或ScenarioRunner时才按其说明单独建环境；不要用它覆盖当前主流程所需的Python 3.10/CARLA 0.9.16环境。

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
