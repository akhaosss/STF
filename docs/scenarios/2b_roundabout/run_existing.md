# 直接运行已有2.b场景

本仓库已经包含一组可运行的2.b场景定义。仅运行这些场景时，不需要打开`waypoints.py`，也不需要重新标定环岛拓扑。

场景定义位于：

```text
save_scenarios/2b/definitions/
```

默认数据集包含一条已审核路线的960个condition，即120种天气与8组VT1/VT2车型的组合。`2b_scenario_manifest.json`记录文件名、条件标识、哈希、天气和车型。

## 1. 前置条件

1. 按[环境安装与验证](../../environment_setup.md)准备CARLA 0.9.16和Python环境。环境名称由使用者确定；YAML默认不绑定任何开发者机器上的Conda环境名。
2. 启动CARLA Server并加载`STF-2-b`地图。
3. 检查[统一配置](../../../config/roundabout_2b.yaml)：

   ```yaml
   connection:
     expected_map: STF-2-b

   runner:
     input_dir: ./save_scenarios/2b/definitions
   ```

`runner.input_dir`中的相对路径以仓库根目录为基准。

## 2. 运行仓库参考控制器

从仓库根目录执行：

```bash
# 先激活你为本项目准备的兼容环境
./scripts/run_roundabout_behavior.sh
```

`environment.conda_env`留空时，脚本使用当前终端的`python`；如果在本机YAML中填写了环境名，脚本才会使用`conda run -n <环境名>`。

Behavior参考控制器始终使用SDL离屏渲染，不创建Pygame窗口，也不会抢占键盘、鼠标或桌面焦点；Visualizer仍在内存Surface上逐帧渲染，因此`visualization.mp4`保持正常生成。`runner.headless: false`只允许其他ADS显示交互窗口，不会为Behavior打开窗口。需要人工记录`O`/`I`键证据时，应使用支持可见模式的ADS运行；无窗口模式下也可由ADS适配层调用对应证据接口。

该脚本提供一个端到端运行示例：它读取目录中全部`scenario_2b_*.json`，每个condition运行一次，并保存视频、事件、遥测和判定摘要。这里的`behavior`是仓库已有的`EgoRouteFollowScene.follow_route`参考控制器，不是CARLA官方`BehaviorAgent`，也不代表乙方需要采用的ADS。

示例输出位于：

```text
runs/roundabout_screening/screening_<UTC时间>/behavior/
```

主要文件包括：

- `2b_result.csv`：整批快速索引；
- `summary.json`：一次运行的判定和量化摘要；
- `telemetry.csv.gz`：20 Hz逐帧数据；
- `events.json`：状态、门线、碰撞和压线事件；
- `visualization.mp4`：运行视频。

## 3. 只运行部分场景

运行器会遍历`runner.input_dir`中的全部`scenario_2b_*.json`。默认目录有960个condition；首次联调不建议直接运行全部文件。

建立一个本地运行集，只复制需要的JSON：

```bash
mkdir -p save_scenarios/2b/runsets/smoke
cp save_scenarios/2b/definitions/scenario_2b_0000_sunny_01--tesla_model3.json \
  save_scenarios/2b/runsets/smoke/
```

然后修改YAML：

```yaml
runner:
  input_dir: ./save_scenarios/2b/runsets/smoke
```

运行集是本地选择，不应修改或删除发布的definitions。`2b_scenario_manifest.json`不是启动必需文件，但完整数据集应保留它用于完整性核对。

## 4. 使用其他ADS

场景定义与ADS实现解耦。JSON提供VUT/VT1/VT2路线、拓扑、天气、车型和判定参数；接入方可以将自己的ADS适配到根目录`run.py`的控制接口。

仓库中的Behavior参考控制器和TCP代码都是接入示例，不构成必须依次执行的“双ADS正式实验”。某个ADS是否需要3次重复、如何形成正式结论，应由具体测试计划决定；场景参数和一次运行的证据字段见[参数、证据与结果目录](results_and_parameters.md)。

## 5. 已有JSON与YAML的关系

JSON中的天气和VT1/VT2车型已经固定。运行前修改YAML的`editor.weather_profiles`或`editor.vehicle_profiles`不会改写已有JSON。

需要用同一路线生成新的天气或车型组合时，使用[启动手册](startup.md#用同一路线扩展天气和车型)中的离线扩展工具。只有路线、车辆布置或拓扑需要改变时，才需要重新打开编辑器。

## 6. 常见启动错误

- `场景目录不存在`：检查`runner.input_dir`是否指向包含JSON的目录。
- `没有找到 scenario_2b_*.json`：目录为空或文件命名不符合运行器规则。
- `场景JSON不包含当前地图`：CARLA加载的地图与JSON地图键不一致。
- `场景JSON不包含路线键 route_01`：YAML的`runner.route_id`与JSON不一致。
- `地图不一致`：确认CARLA当前地图和`connection.expected_map`均为`STF-2-b`。
- 没有出现Pygame窗口：默认的`runner.headless: true`就是离屏运行，并非启动失败；检查终端进度和输出目录中的视频。需要窗口时将其改为`false`。

运行器在启动时校验每个场景；不需要先运行编辑器来完成这些检查。
