# 2.b 参数、证据与结果目录

> 本文回答三个问题：参数从哪里来、它对应国标还是仿真实现、运行后到哪里找证据。直接运行发布数据见[已有场景运行说明](run_existing.md)，修改路线见[编辑与扩展](startup.md)。

## 1. 四层对象不能混用

| 层级 | 含义 | 是否重复绘制 | 稳定标识 |
|---|---|---:|---|
| route | 一次人工绘制的VUT起点/路线、VT1起点/路线、VT2位置及STEP 1拓扑 | 是，只有路线改变才重画 | `route_id` + `route_definition_fingerprint` |
| condition | route加天气、VT1/VT2车型、能力分支、计划出口和工程参数 | 否，由编辑器自动展开 | 人类可读`condition_id` + `condition_fingerprint` |
| trial | 同一个condition的一次重复；需要3次结论时使用trial 1/2/3 | 否，由重复评估启动器展开 | `matrix_id` + `trial_index` + `trial_seed` |
| attempt | 某个trial因建场或证据无效后的重试 | 否，由运行器补测 | `attempt_index` |

`condition_fingerprint`是完整条件的SHA-256；目录只使用其前10位，例如`c_39f6d72b3a`，完整值保存在JSON。旧字段`route_fingerprint`在正式重复元数据中继续保留用于兼容，但其历史含义实际是“完整条件指纹”；新数据应优先读`condition_fingerprint`。人工路线本身应读`route_definition_fingerprint`。

## 2. YAML用户参数

所有日常可调输入位于 [config/roundabout_2b.yaml](../../../config/roundabout_2b.yaml)。

| YAML路径 | 类型/单位 | 当前值 | 作用 | 参数性质 |
|---|---|---:|---|---|
| `environment.conda_env` | 环境名或空字符串 | 默认空 | 留空时使用当前激活环境；填写时由脚本执行`conda run -n` | 本机运行环境 |
| `environment.carla_root` | 路径 | 空 | 自动发现失败时指定CARLA根目录 | 运行环境 |
| `connection.host/port` | 地址/端口 | `127.0.0.1:2000` | CARLA RPC连接 | 运行环境 |
| `connection.wait_timeout_s` | s | 60 | 启动器等待Server的上限 | 工程参数 |
| `connection.expected_map` | 地图名 | `STF-2-b` | 防止场景误用于另一张地图 | 审计约束 |
| `editor.save_dir` | 路径 | `save_scenarios/2b/definitions` | 场景定义输出；该目录也随仓库发布 | 数据管理 |
| `editor.seed` | 整数 | 41798 | 场景展开和trial seed的根种子 | 可复现参数 |
| `editor.speed_limit_kmh` | km/h或`null` | `null` | OpenDRIVE无可用限速时的人工确认回退 | 工程参数，不是国标给定值 |
| `editor.conflict_sync.target_headway_s` | s | 1.0 | 期望VT1比VUT先经过共同冲突点的时间 | 工程参数 |
| `editor.conflict_sync.tolerance_s` | s | 0.5 | 上述领先时间允许窗口 | 工程参数 |
| `editor.weather_profiles` | 列表 | 全部内置天气 | 同一路线自动展开天气 | 场景条件 |
| `editor.vehicle_profiles` | 列表 | 8组 | 只展开VT1/VT2车型，VUT不随之变化 | 场景条件 |
| `runner.input_dir` | 路径 | definitions目录 | 运行器读取范围 | 数据管理 |
| `runner.repetitions` | 次 | 3 | 可选重复评估的trial数量 | 国标重复要求的实现参数；单次示例不使用 |
| `runner.max_invalid_retries` | 次 | 2 | 重复评估时每个trial最多补测次数 | 工程参数 |
| `runner.experiment_root` | 路径 | `runs/roundabout_formal` | 可选重复评估批次根目录 | 数据管理 |
| `runner.screening.output_root` | 路径 | `runs/roundabout_screening` | 一次筛选根目录 | 数据管理 |
| `runner.screening.max_invalid_retries` | 次 | 0 | 筛选是否补测 | 工程参数 |
| `ads.tcp.model_path` | 文件 | 默认空 | 可选TCP示例的checkpoint | 可选控制器配置 |
| `ads.tcp.require_cuda` | bool | false | 运行TCP示例时是否强制CUDA | 运行环境 |

天气与车型做笛卡尔积：当前`120种天气 × 8组车型 = 每条route生成960个condition`。这不会重新绘制路线。

## 3. JSON中的标准参数与工程参数

### 国标明确或直接派生的场景字段

| JSON字段 | 含义 | 来源/对应关系 |
|---|---|---|
| `roundabout_test.standard_clause` | `GB/T 41798-2022 6.2.2` | 标准条款标识 |
| `topology.arm_count/arms` | 不少于3个物理接入方向，每个至少一进一出 | STEP 1人工标定、程序展开、用户复核 |
| `planned_exit` | VUT从出口2或3驶出 | VUT路线穿越审核OUT门线后自动编号 |
| `roundabout_capable` | 是否具备环岛能力 | STEP 0用户确认 |
| `vt1.target_speed_kmh` | 15 km/h | 国标明确值，程序固定 |
| `vt1.exit_number` | VT1从出口1驶出 | 国标要求和路线门线校验 |
| `vt2.motion` | stationary | 国标要求，程序固定 |
| `entry_gate/exit_gates/downstream_entry` | 入口、出口和下游第1入口的有方向判定面 | 从审核拓扑及开放路线自动派生 |

### `roundabout_test.engineering`仿真参数

这些值用于把标准中的自然语言变成CARLA可执行条件，不能称为国标原始数值。

| 字段 | 单位 | 当前规则/默认值 | 用途 |
|---|---:|---:|---|
| `vt1_initial_upstream_min_distance_m` | m | 按路线与时序自动算 | VT1建场、加速、稳速及交汇所需初距 |
| `vt1_entry_upstream_min_distance_m` | m | 路线分析值 | VUT到达入口时VT1仍在上游的余量 |
| `vt1_setup_distance_budget_s` | s | 2 | VT1建场预算 |
| `vt1_stable_duration_s` | s | 1 | 15 km/h连续稳定窗口 |
| `vut_approach_speed_assumption_kmh` | km/h | 15 | 仅用于编辑器时序估算，不是VUT受测速度要求 |
| `vut_approach_time_budget_s` | s | 路线计算，运行上限15 | VUT到入口的统一时序预算 |
| `vt1_conflict_headway_target_s/tolerance_s` | s | YAML 1.0/0.5 | 自动放行线与有效领先窗口 |
| `vt1_release_remaining_m` | m | 自动算 | VT1到放行位置剩余路线长度 |
| `vt2_initial_upstream_distance_m` | m | 2 | VT2在下游入口门线上游的默认布置距离 |
| `vt2_stationary_speed_threshold_mps` | m/s | 0.1 | 判定VT2仍静止 |
| `stop_speed_threshold_mps` / `stop_duration_s` | m/s、s | 0.1、1.0 | 入环后停车判定 |
| `emergency_brake_deceleration_mps2` | m/s² | 4.0 | 急减速阈值 |
| `emergency_brake_threshold/duration_s` | 比例、s | 0.8、0.2 | 制动请求急刹阈值与持续窗 |
| `speed_limit_tolerance_kmh` | km/h | 0.5 | 限速数值容差 |
| `speed_limit_unobservable_duration_s` | s | 0.5 | 连续缺失限速证据后判INVALID |
| `route_completion_distance_m` | m | 3 | 路线完成位置容差 |
| `exit_completion_distance_m` | m | 2 | 出口下游及车道检查距离 |
| `indicator_lookback_s` | s | 3 | 驶出门线前转向灯证据窗口 |
| `incapable_observation_s` | s | 10 | 不具备能力分支的入口前观察窗 |
| `scenario_timeout_s` | s | 120 | 单次尝试总超时 |
| `timeline_sample_interval_s` | s | 0.05 | 20 Hz CARLA真值遥测 |
| `camera_frame_timeout_s` | s | 0.5 | TCP当前帧等待上限 |

每个condition的`condition.json`会保存完整场景快照，所以最终实际值应以该文件为准，不应只依赖本表默认值。

## 4. 仿真证据配置

本项目使用`evidence_profile=stf_carla_simulation`：

- 固定同步步长0.05 s，逐帧遥测20 Hz；按用户决策不提升到物理设备条款中的50 Hz。
- 视频为512×256、20 fps、H.264可视化证据；按用户决策不要求1080p。
- 运动学来源为CARLA ground truth，不是外部GNSS/IMU测量。
- 仿真无物理座舱和座舱音频，记录`not_applicable`及原因。
- 因上述差异，结果明确记录`physical_field_test_compliance_claimed=false`，不能仅凭仿真结果宣称完成物理场地认证。

20 Hz的`telemetry.csv.gz`逐帧包含：

- VUT/VT1/VT2的位置、roll/pitch/yaw、世界坐标速度/加速度、角速度；
- 车体纵向/横向速度与加速度；
- 请求控制和CARLA实际控制（油门、方向、制动、手刹、倒车、档位）；
- ADS是否已激活和控制来源；
- road/section/lane、路线进度、完成比例和横向偏移；
- VUT到VT1/VT2的平面质心距离，以及按两车相对速度在视线方向投影得到的TTC；
- 灯光原始位掩码及可读状态。

`summary.json`还保存试验时长、行驶距离、平均/最大速度、最小车距、最小TTC、VT1速度均值/标准差、冲突点时间差、最大减速度和各项判定。距离为车辆参考点的二维距离，未扣除包围盒；TTC只在相对速度正在闭合时有值，不应当作标准原始阈值。`average_velocity`仅作为兼容别名，与`average_speed_mps`一致，不再表示终帧速度。

## 5. 结果目录

可选重复评估批次：

```text
runs/roundabout_formal/
└── batch_<UTC时间>/
    ├── roundabout_experiment_manifest.json
    ├── prepared_scenarios/<UTC时间>/
    ├── behavior/
    │   ├── 2b_result.{md,json,csv,pkl}
    │   └── route_0001_exit2_capable/
    │       └── sunny_01--tesla_model3__c_39f6d72b3a/
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

仓库参考控制器的单次示例使用`runs/roundabout_screening/screening_<UTC时间>/behavior/.../screening/attempt_01/`，每个condition只运行一次，不生成3次重复结论。

文件关系：

| 文件 | 用途 |
|---|---|
| `roundabout_*_manifest.json` | 整批YAML哈希、CARLA版本、输入定义、ADS顺序和完成状态 |
| `2b_result.csv/md` | 兼容性批次索引与快速筛选 |
| `2b_result.json/pkl` | 兼容性总账；新分析优先读取分层文件 |
| `condition.json` | 精确场景配置、运行环境、标准/工程参数对应关系 |
| `summary.json` | 一次attempt的轻量判定和量化摘要 |
| `telemetry.csv.gz` | 20 Hz完整时序数据 |
| `events.json` | 状态迁移、门线、碰撞、压线及夹具事件 |
| `visualization.mp4` | 仿真可视化视频 |
| `artifact_manifest.json` | 文件相对路径、字节数和SHA-256 |
| `aggregate.json` | 同一控制器、同一condition的3次判定与均值/标准差/最小/最大 |

`aggregate.json`中的`quantitative_statistics`用于比较重复运行的稳定性。只有测试计划采用3次重复判定时，聚合`pass=true`才要求trial 1、2、3选出的有效attempt全部PASS。Behavior和TCP只是仓库接入示例，不要求组合成同一个正式结论。
