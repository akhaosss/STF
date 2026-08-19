# 环形路口2.b编辑与场景扩展

本文件说明如何修改环岛路线，以及如何用一条路线生成天气和车型组合。仓库已经包含可运行的场景定义；只想运行现有数据时，请直接阅读[直接运行已有2.b场景](run_existing.md)，无需启动编辑器。

编辑器和运行器共用[统一配置](../../../config/roundabout_2b.yaml)。常用参数在YAML中调整，不需要手工拼接`waypoints.py`或`run.py`命令行。参数单位和来源见[参数、证据与结果目录](results_and_parameters.md)。

仓库提供两个控制器接入示例：

1. `behavior`：仓库已有的`EgoRouteFollowScene.follow_route`参考控制器，不是CARLA官方`BehaviorAgent`；
2. `tcp`：需要单独checkpoint的可选模型示例。

接入方可以替换为自己的ADS，不要求按Behavior→TCP顺序执行。仓库保留双控制器和3次重复能力，用于需要对比或重复评估的项目；它不是运行场景数据的前置条件。

## 1. 修改统一配置

打开：

```bash
vim config/roundabout_2b.yaml
```

配置文件中的每个可调参数均有中文注释，主要包括：

- Conda 环境和 CARLA 根目录；
- CARLA Server 地址、端口、等待时间和预期地图；
- 编辑器JSON输出目录、随机种子、限速回退、天气配置、VT1/VT2车型组合，以及统一的VT1/VUT冲突时间差；
- 运行输入目录、补测次数和结果目录；
- 可选TCP checkpoint和CUDA要求。

所有相对路径均以仓库根目录为基准。至少确认目标地图：

```yaml
connection:
  expected_map: <目标地图名>
```

只有运行TCP示例时才需要填写`ads.tcp.model_path`。

如果地图能提供 OpenDRIVE 限速，保持 `editor.speed_limit_kmh: null`；只有地图缺少限速证据时才填写经过确认的工程限速。

### 用同一路线扩展天气和车型

编辑器复用仓库已有的天气库。`editor.weather_profiles`选择天气，`editor.vehicle_profiles`选择VT1/VT2车型；按`S`时对两份列表做组合。当前默认`preset: all`展开15类×8档=120种天气，再与8组目标车型组合，因此一条路线生成960份场景定义。VUT仍使用被测ADS的固定Ego车型，不参与车型扩展。

```yaml
editor:
  weather_profiles:
    - id: all_builtin_weather
      preset: all

  vehicle_profiles:
    - id: tesla
      vt1_model: vehicle.tesla.model3
      vt2_model: vehicle.tesla.model3
    - id: audi
      vt1_model: vehicle.audi.tt
      vt2_model: vehicle.audi.tt
```

把`preset: all`改为具体天气时，`level`范围为1～8；也可使用`parameters`逐项填写CARLA天气参数。车型字符串必须是当前CARLA Server中存在的`vehicle.*` blueprint。编辑器启动时会读取CARLA车辆蓝图库并核对8组车型，缺失时直接列出具体ID。路线、车辆位置和拓扑只绘制一次，天气与车型只改变生成JSON中的`weather`和`other_actors.center[].model`。

### 已经画好的路线无需重画

已有2.b JSON可以直接用离线扩展工具生成天气×车型场景。工具会把旧版同一路线的`trial_01/02/03`自动去重为一条基础路线，保留VUT/VT1路线、VT2位置、拓扑、门线和工程参数，只替换天气与VT1/VT2车型：

```bash
# 只查看路线数、输出数量和预计体积，不写文件
python3 tools/expand_roundabout_scenarios.py \
  --input-dir save_scenarios/2b \
  --output-dir save_scenarios/2b/definitions \
  --dry-run

# 正式生成；目标目录已有同名文件时会拒绝覆盖
python3 tools/expand_roundabout_scenarios.py \
  --input-dir save_scenarios/2b \
  --output-dir save_scenarios/2b/definitions
```

确认需要重建同名场景时追加`--overwrite`。工具使用紧凑JSON降低磁盘占用，并生成`2b_scenario_manifest.json`，其中记录每个文件的来源路线指纹、天气、车型、大小和SHA-256。该工具只处理JSON，不需要重新打开pygame编辑器，也不会修改输入目录中的原始路线文件。

## 2. 启动 CARLA

使用CARLA源码/UE4Editor版本时：

```bash
conda activate carla0916
cd <CARLA_ROOT>
./CarlaUE4-with-coredump.sh -windowed -benchmark -fps=20 -carla-port=2000
```

CARLA应加载YAML中`connection.expected_map`指定的地图，当前发布数据使用`STF-2-b`。

## 3. 一键启动环岛编辑器

新终端中执行：

```bash
./scripts/start_roundabout_editor.sh
```

脚本自动完成：

- 读取 YAML 中的 Conda 环境；
- 补充 CARLA `PythonAPI/carla`；
- 检查并等待 CARLA Server；
- 校验当前地图；
- 创建 JSON 输出目录；
- 启动 `waypoints.py --scenario 2b`。

启动器不会代替用户启动CARLA Server。若Server尚未监听YAML中的地址和端口，终端会立即显示“CARLA尚未就绪”并持续重试，超过`connection.wait_timeout_s`后给出明确错误；此时应先启动CARLA，而不是修改或重装编辑器。

编辑器内操作：

- 左上角默认显示约六行的紧凑状态栏，只保留当前步骤、总体进度、保存状态和快捷键；按 `H` 才展开 `STEP 0`～`STEP 7` 完整流程。黄色 `>>` 是当前建议步骤，`OK` 表示已经完成。STEP 0和STEP 1必须先完成，后续车辆对象可灵活放置。
- STEP 0测试分支：按 `Enter` 接受当前能力分支，或按 `R` 切换并确认；完成后进入STEP 1。
- STEP 1拓扑标定与审核：把鼠标移到车道上，编辑器会预览“固定屏幕长度的横向门线＋纵向大箭头”。绿色 `NEXT Axx IN` 表示进口，蓝色 `NEXT Axx OUT` 表示出口。对每个物理接入方向先标靠近环岛的进口，再标同一方向的出口；当前五向环岛应完成5对。标定完成后按 `P`，程序检查重复/缺失车道、吸附关系和方向，并结合CARLA左右邻接与门线横断面空间扫描展开同向Driving Lane；即使每条车道被建成不同`road_id`也能识别。双车道应显示两份相同的 `Axx IN` 或 `Axx OUT`，面板同时逐arm列出`IN n / OUT n`。此时仍停留在STEP 1；用户逐项检查地图高亮，确认无误后按 `Enter` 才进入STEP 2。最后一点标错用 `Backspace/Ctrl+Z`，全部重做用 `X`。
- 同一物理arm存在多条并行同向车道时，只在其中一条代表车道上点击一次；程序会自动纳入同一道路、同一section内CARLA相邻的同向Driving Lane，不要把两条并行进口车道重复标成两个arm。如果OpenDRIVE将它们建模为彼此独立的接入道路，或它们确实分别接入环岛，则分别标定。
- STEP 1拓扑会按“CARLA完整地图名 + OpenDRIVE SHA-256”保存到`config/roundabout_topology/`。同一地图再次启动时自动加载并停在审核界面：检查正确按`Enter`；发现错误则左键点击对应IN/OUT高亮，再在正确车道右键重设。地图或OpenDRIVE发生变化时不会加载旧坐标，而是进入首次右键逐臂绘制流程。
- `V`后`Ctrl + 左键`：完成STEP 1后放置 VUT。程序会沿CARLA `next()`方向，以首先到达的审核IN门线确定VUT进口arm；进入环岛后后续可达的其他入口不参与起点归属。只有两个arm在相同最短拓扑距离同时到达才提示真正歧义。随后地图高亮建议汇入口、供VT1使用的出口1，以及可供VUT选择的出口2/3，再用 `Alt + 右键` 绘制路线。每次点击会收集鼠标附近多条候选车道，并在加入锚点前逐条运行有界车道图搜索：同时检查所有前向分支以及左右合法同向Driving Lane。程序优先选择可达、接近鼠标、变道少且不绕行的候选，而不是锁死几何最近的车道；最终选择的`road/section/lane/s`会显示并固定保存。成功才接收并更新黄色真实草稿线；失败点不会加入路线、不会写入撤销历史，失败段标红，可直接重新点击正确车道，无需先撤销。最后一个锚点必须沿蓝色箭头方向穿过所选OUT门线并落在门线下游。
- STEP 3按`Enter`确认VUT路线时，程序先依据STEP 1审核进口门线检查VUT起点至少有3m上游余量。最终运行时入口是VUT路线与VT1环流路线的实际汇合门线，只有VT1路线完成后才能确定；因此STEP 5按`Enter`时会立即进行第二次、权威的入口余量检查。若不足，会停留在STEP 5并用中文提示需要向上游移动的最小距离，不会拖到`S`才首次报告。
- `Enter`：STEP 0确认测试分支；P完成程序拓扑审核后，在STEP 1确认用户目视审核；之后用于确认当前选中的动态车辆路线。选中VUT时确认STEP 3，并用STEP 1拓扑、实际车道序列和门线穿越推导 `VUT IN GATE`、`EXIT n` 与 `DOWNSTREAM-1 IN`；选中VT1时确认STEP 5并进入STEP 6。最终运行时汇入门线要等VUT、VT1两条开放路线都完成后再由它们的实际汇合位置生成。
- Enter检查失败时，错误会在pygame紧凑面板中自动换行并保持可见。2.b不会再调用全局规划器连接相邻锚点，而是使用有界A*搜索CARLA车道图：图边包含全部有向`next()`前向分支，以及OpenDRIVE允许的左/右同向Driving Lane变道。相比普通BFS，A*能用距离引导并对横向变道增加代价，优先保持当前车道。每段最多允许2次变道；明确实线、对向车道、过远的相邻道路不加入搜索图。错误会列出前向边、合法横向边、搜索上限和最近距离。这样既能处理复杂多车道位置，又不会把附近锚点静默变成绕行地图的千米级路线。
- `T` 后 `Ctrl + 左键`：放置 VT1；选中后用 `Alt + 右键` 绘制从出口 1 驶出的路线，画完按 `Enter` 确认。VT1路线首次到达VUT汇入冲突点时，编辑器会立即预告起点上游距离是否不足；STEP 5按`Enter`时使用与最终保存完全相同的时序距离公式正式校验，失败则停留在STEP 5，不会拖到`S`才首次报告。
- `Y` 后 `Ctrl + 左键`：在地图高亮的下游第1入口绿色IN车道上选择VT2车道；VT2不画路线。程序会立即核对有向lane连通性并在必要时调整到门线上游2m。放置后`Enter`只确认“VT2静止且无路线”，然后按`S`执行STEP 7。
- VUT路线确认后，程序会沿CARLA有向车道拓扑反向搜索推荐放置区间：橙色路点/箭头表示能够到达VUT冲突点且满足当前动态上游距离的VT1环流区间；紫色路点/箭头表示下游第1入口门线上游2～30m的VT2进口区间。若自定义OpenDRIVE把VUT和环流路径建成没有共同`previous()`节点的并行连接道，程序会自动从出口1反向追踪并以两条真实路线的首次近距离相遇确定冲突位置，同时排除各arm的进口道路分支。推荐色只辅助选择，不代替Ctrl+左键确认；无法由CARLA拓扑或出口1路径证明可达的附近道路不会着色。
- STEP 6放置VT2后按`Enter`会运行一次完整场景预检；只有VUT、VT1、VT2、最终汇合门线、出口关系及工程余量全部通过，界面才提示进入STEP 7。`S`仍保留最终配置一致性保护，但不应再是首次发现几何问题的步骤。
- 自定义OpenDRIVE可能在进口上游、连接段和门线附近使用不同的`road_id/section_id/lane_id`。只要CARLA有向拓扑证明VT2所在车道能够到达已审核的下游进口门线，编辑器会同时保存“VT2实际车道”和“门线审核车道”，不会仅因编号在连接处变化而拒绝保存。若保存前仍出现车道问题，界面会用中文列出实际车道和允许车道编号。
- `L`：显示/隐藏完整拓扑几何。STEP 1确认后默认仍为每个物理arm保留一组代表性IN/OUT彩色门线和方向箭头；按`L`才展开该arm的全部平行车道标记。它不控制文字。
- `R`：切换具备/不具备环岛行驶功能分支，并确认STEP 0。
- `Backspace` 或 `Ctrl + Z`：撤销最近一次已经成功的编辑操作，包括车辆放置/删除、路线点、清空路线、角色修改和能力分支切换。可连续撤销，最多保留 100 步；选择车辆、缩放和平移不进入撤销记录。
- `C`：清除当前 VUT/VT1 整条路线；误清后可立即撤销。
- `Delete`：STEP 1 中可排除左键选中的错误“程序展开车道”；排除结果在
  `Enter` 确认 STEP 1 后写入地图拓扑缓存。其他步骤用于删除选中车辆。
- STEP 1标定与审核期间始终显示`NEXT Axx IN/OUT`及已标定的`Axx IN/OUT`文字，避免仅凭颜色误标；这一阶段`H`不会隐藏必要的拓扑身份文字。按`Enter`确认STEP 1后，地图默认只保留不同颜色的点、门线、箭头与路线，不再显示`Axx IN/OUT`、`EXIT n`、`V/T`锚点编号或`VUT/VT1/VT2`名称。
- `H`：STEP 1确认后，同时切换详细步骤面板和地图文字；需要复核编号时按`H`，完成后再按一次恢复简洁视图。颜色固定为：进口绿色、出口蓝色、VUT及其入口青色、出口1黄色、出口2橙色、出口3橙红色、VT2及下游入口紫色。
- 高倍缩放时，稀疏路线锚点之间的屏幕距离可能很大。编辑器只在可见锚点附近绘制有限长度的路线尾段；两端均在屏幕外的线段不绘制，避免形成横贯窗口的彩色渲染条。缩小视图后完整连接线会自然恢复。

按`S`成功后，终端和pygame会显示输出路径。默认是`save_scenarios/2b/definitions/`，其中包含场景定义JSON和`2b_scenario_manifest.json`。数量按实际天气数乘以车型组合数计算；若YAML修改了配置或输出目录，以界面和manifest为准。
- `S`：校验并按天气×车型组合生成场景定义，不生成重复试验副本。
- `Q`：退出。

`S`是一次编辑会话的提交边界：保存成功后编辑器会清空当前场景和撤销历史，`Ctrl + Z`不会删除已经写出的JSON。若保存后才发现配置错误，应移走对应的场景定义后重新绘制；其他天气或车型定义可以继续保留。

### 路线确认颜色与“所见即保存”

- 按Enter前，VUT/VT1手工锚点均为黄色空心点；每个已接受锚点都已经完成即时车道搜索，黄色细线显示当前实际稠密草稿，而不是锚点间直线。它尚未完成入口/出口和国标关系复核，因此仍不是正式运行路线。
- 按Enter通过后，程序生成的约1m级真实路线会替换锚点预览：VUT为青色，VT1为橙色，并沿路线显示方向箭头。此时显示的不是锚点之间的直线，而是CARLA实际有向车道序列。
- 若某次Alt+右键的局部搜索失败，候选点会立即被拒绝；已经成功追踪的部分显示为灰色，失败的候选段显示为红色。直接在分叉前后或正确车道重新点击即可，不需要先按Backspace。Backspace只用于撤销此前已经成功接收的锚点。
- Enter确认会冻结路线内容和指纹。后续拓扑分析、STEP 6综合预检以及S保存都复用同一缓存，不会在保存时重新规划；JSON中的`roundabout_test.vut.route_fingerprint`和`vt1.route_fingerprint`可用于核对。
- 修改车辆起点、增加/清空路线点或删除车辆会立即使对应路线失效，必须重新按Enter确认。出口必须同时满足三项证据：穿过有限宽度的OUT横门线、交点附近稠密路线属于该审核OUT车道、路线方向与出口箭头一致。仅横穿出口道路、擦过门线端部或经过门线无限延长线均不算驶出；连续道路较早产生的辅助几何交点不会覆盖路线最终明确穿过的目标出口。

### 路线点间隔

手工点是“路线导航锚点”，不是最终控制轨迹。每次Alt+右键时程序就使用CARLA前向分支和合法左右变道关系，把当前候选段补全为约1m级的连续路线，因此不需要每隔1～2m密集点击。Enter复用已完成的分段结果做正式关系复核，保存继续复用Enter确认结果。

- 普通路段：相邻锚点推荐 `10～20 m`。
- 无分叉的简单直线：可放宽到 `20～30 m`。
- 分叉、环岛入口、环岛内需要确定行驶方向的位置、目标出口前后：推荐 `5～10 m`。
- VUT 路线应至少覆盖入口前、环岛内、目标出口以及出口下游；VT1 路线应覆盖其起点、环岛内、出口 1 和出口下游。

界面中的 `V1、V2...` 是VUT手工路线锚点，`T1、T2...` 是VT1手工路线锚点。车辆图标本身是路线真实起点，因此界面会分别绘制 `VUT→V1` 和 `VT1→T1` 的连接段；保存时也会把车辆起点作为稠密化路线的首点。连接段不代表额外的人工锚点。

每次添加路线点后，终端会显示它与上一个锚点（首点则与车辆起点）的直线距离。超过30m时仍允许添加，但会提示在可能存在分叉的位置补点。局部搜索上限为`min(120m, max(30m, 3×锚点直线距离+20m))`；若Enter时报无法连通，应撤销最后一点，再在分叉前后补充锚点，而不是等待S保存时才处理。

### VT1和VT2放置位置

VT1和VT2不是放在任意邻近车道：

物理arm、VUT汇入口、出口1/2/3和下游第1入口的严格定义见[场景说明“国标场景定义”](README.md#国标场景定义)。五臂环岛是5个物理arm；同一arm中错开的进口和出口仍分别按实际车道口排序，不能用二者平均位置代替。

- **VT1**：放在环岛的环形行车道上，不是VUT驶来的接入道路。沿界面绿色箭头所示环流方向观察，VT1应位于到达VUT汇入口之前的上游位置，车头沿环流方向；然后绘制其沿环岛行驶并从出口1驶出的路线。为了让VT1完成加速并以15 km/h稳定到达，起点还必须有足够上游距离；不足时编辑器会给出所需距离，应沿环流反方向把VT1起点继续前移。
- **VT2**：从VUT入口开始沿环流方向寻找遇到的下一个车辆接入口，在该接入道路中绿色箭头朝向环岛的**进口车道**、入口线之前放置，车头朝向环岛。不要放到箭头离开环岛的出口车道。VT2保持静止，不绘制路线。
- “下游第1入口”描述的是VT2所在的车辆入口；“出口1”描述的是VT1准备驶出的第一个出口，两者不是同一个概念，也不要求位于同一接入方向。

紧凑面板到达STEP 4或STEP 6时会自动用彩色专用提示替换普通“最近操作”行；按 `H` 可同时查看两辆目标车的完整位置规则。

## 4. 运行参考控制器示例

该入口不检查TCP checkpoint，也不会自动进入TCP。每个场景定义执行一次，适合验证数据和展示接入流程：

```bash
./scripts/run_roundabout_behavior.sh
```

启动范围由 `config/roundabout_2b.yaml` 的 `runner.input_dir` 决定。启动器会在运行前
动态统计并打印该目录中的有效`scenario_2b_*.json`数量，不使用文档中的固定数量。
当前一次有效绘制按`120种天气 × 8组目标车型`生成960个场景定义；`bp/`中的旧路线
不会被读取。筛选阶段使用 `runner.screening.max_invalid_retries: 0`，INVALID不会自动补测。

参考运行会在`runner.screening.output_root`下建立独立的
`screening_<UTC时间>/behavior/`批次目录。每个condition有
`screening/attempt_01/visualization.mp4`、`summary.json`、`events.json`和20 Hz
`telemetry.csv.gz`；`2b_result.csv`适合快速排序筛选。该示例每个condition只运行一次，
不形成3次重复结论。完整的直接运行步骤见[直接运行已有场景](run_existing.md)。

## 5. 可选：双控制器重复对比

需要用相同场景对比仓库Behavior和TCP示例时执行：

```bash
./scripts/run_roundabout_experiments.sh
```

启动器会在开始第一组实验前统一检查：

- 输入目录中至少存在一份`scenario_2b_*.json`场景定义，且不能混放旧版trial文件；
- TCP checkpoint 已填写且存在；
- CUDA 要求满足 YAML 配置；
- CARLA 可连接且地图正确。

随后依次运行：

```text
每份场景定义自动展开3次
        │
        └── <experiment_root>/batch_<UTC时间>/
              ├── behavior ADS
              └── tcp ADS
```

任一控制器启动异常时，对比批次标记为未完成并停止后续环节。该流程是可选示例，不限制接入方使用其他ADS或独立测试计划。

## 6. 结果

### 在编辑器风格地图中回放实际轨迹

轻量`2b_result.pkl`只作为兼容批次索引；每个attempt的`telemetry.csv.gz`保存逐帧VUT、VT1、VT2运动学。CARLA Server加载对应地图后，可将规划路线和实际轨迹叠加查看：

```bash
./scripts/view_roundabout_run.sh \
  runs/.../route_0001_exit2_capable/<condition>/trial_01/attempt_01/telemetry.csv.gz
```

查看器同时接受同目录的`summary.json`和历史`2b_result.pkl`。它默认从摘要的`input_file`读取精确场景JSON；找不到时可把场景JSON作为第二个参数。青色虚线是规划VUT路线，白色实线是实际VUT轨迹；橙色虚线是规划VT1路线，黄色实线是实际VT1轨迹，紫色点是VT2。入口与出口门线继续沿用编辑器颜色。

- `Space`：从头播放或暂停；
- `←/→`：逐帧检查；
- `Home/End`：跳到首帧/末帧；
- `F`：恢复完整路线视图；
- `H`：显示或隐藏车辆、入口和出口文字；
- 鼠标中键拖动画面，滚轮缩放，`Q`退出。

该视图只读取结果和场景定义，不修改路线，也不会启动新试验。它用于区分“车辆真实偏离规划路线”和“同一物理道路被CARLA报告为不同OpenDRIVE connector编号”。

默认输出结构：

```text
runs/roundabout_formal/
└── batch_<UTC时间>/
    ├── roundabout_experiment_manifest.json
    ├── prepared_scenarios/<UTC时间>/
    ├── behavior/
    │   ├── 2b_result.{md,json,csv,pkl}
    │   └── route_0001_exit2_capable/
    │       └── <condition_id>__c_<短指纹>/
    │           ├── condition.json
    │           ├── aggregate.json
    │           └── trial_01/attempt_01/
    │               ├── summary.json
    │               ├── telemetry.csv.gz
    │               ├── events.json
    │               ├── visualization.mp4
    │               └── artifact_manifest.json
    └── tcp/...
```

可选对比流程的联合清单记录YAML哈希、地图、CARLA版本、源场景定义、重复实例、两个控制器的执行顺序和完成状态。两组结果分别保存在各自的`2b_result.md`和condition目录中，不合并成一个通过结论。字段、单位、指纹含义和仿真证据边界见[参数、证据与结果目录](results_and_parameters.md)。

## 7. 常见错误

- `请填写 TCP checkpoint`：修改 `ads.tcp.model_path`。
- `混合了场景定义和旧版三次试验文件`：把新版定义保存在YAML默认的`definitions/`独立目录，不要与旧版`trial_01/02/03`混放。
- `地图不一致`：加载 YAML 指定地图，或修正 `connection.expected_map`。
- `没有可用 CUDA`：修复 CUDA环境；仅在确认允许 CPU 实验时将 `ads.tcp.require_cuda` 设为 `false`。
- `等待 CARLA 超时`：确认 Server 地址、端口以及 CARLA 是否完成启动。

国标场景、当前仓库场景、逐项对应关系和判定说明见 [2.b场景定义](README.md)。
