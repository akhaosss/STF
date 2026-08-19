# CARLA Tripo StaticMesh 距离场崩溃处理说明

## 1. 目的与适用范围

本文档记录 CARLA/Unreal Engine 4.26 打开或保存部分 `tripo_node` 静态网格时发生崩溃的原因、临时规避方案、批量处理方法、验证步骤和回滚方法。

当前处理范围：

- Unreal 项目：`/home/fsm/Carla/carla/Unreal/CarlaUE4`
- 资产目录：`/Game/1a/Static/Terrain/1a`
- 目标资产：路径或名称包含 `tripo_node` 的 `StaticMesh`
- 批处理脚本：`disable_tripo_distance_fields.py`

这项修改只处理 CARLA 静态网格的 Mesh Distance Field 构建，不改变 SafeBench 的仿真循环、Actor 创建、评分和清理，也不改变 Bridge 或 Autoware 的职责。

## 2. 故障现象

崩溃的核心报错为：

```text
Assertion failed: (Index >= 0) & (Index < ArrayNum)
Array index out of bounds: N from an array of size N
```

主要调用链：

```text
GenerateSignedDistanceFieldVolumeData
  -> TkDOPTree::Build
    -> TkDOPNode::SplitTriangleList
```

这说明崩溃发生在 UE4.26 为 StaticMesh 生成 Signed Distance Field 时的 kDOP 三角形空间划分阶段，不是 CARLA 运行时车辆控制、SafeBench 或 Autoware 导致的错误，也没有证据表明它是内存耗尽。

## 3. 已确认的样本

截至 2026-08-13，该目录发现 137 个 `tripo_node` 资产：

- 12 个超过 1,000,000 三角形；
- 125 个约在 100,000～500,000 三角形之间；
- 两次已确认崩溃都发生在约 200 万三角形的网格上。

已确认记录：

| 资产 | 三角形数 | 结果 |
| --- | ---: | --- |
| `1a_tripo_node_3236ec6a_PropNode` | 137,104 | 距离场成功生成 |
| `1a_tripo_node_2ad13da1_PropNode` | 1,990,457 | kDOP 数组越界崩溃 |
| `1a_tripo_node_26d632c4_PropNode` | 1,945,215 | 相同调用链再次崩溃 |

因此不能仅根据名称断定所有 `tripo_node` 都会崩溃。高面数、退化三角形、接近零的切线/副法线以及异常拓扑会显著提高触发 UE4.26 距离场构建缺陷的概率。三角形数只是风险指标，不是严格的安全边界。

当前识别出的 12 个百万面高风险资产为：

| 资产后缀 | 三角形数 |
| --- | ---: |
| `2ad13da1_PropNode` | 1,990,457 |
| `9768efc7_PropNode` | 1,986,010 |
| `4ee74bb5_PropNode` | 1,985,496 |
| `73239115_PropNode` | 1,975,655 |
| `4f8c6209_PropNode` | 1,974,695 |
| `4f8c6209_PropNode175` | 1,974,693 |
| `4f8c6209_PropNode174` | 1,974,692 |
| `93d4cb13_PropNode172` | 1,961,654 |
| `93d4cb13_PropNode` | 1,961,654 |
| `26d632c4_PropNode` | 1,945,215 |
| `6ab3890c_PropNode` | 1,939,697 |
| `9cc3ed62_PropNode` | 1,402,163 |

## 4. 处理策略

### 推荐方案：对全部 Tripo 环境网格关闭单资产距离场

如果这些资产是建筑、道路周边、植被或其他装饰环境，并不依赖距离场效果，建议将全部匹配资产的以下属性设为 `0.0`：

```text
LOD 0 -> Build Settings -> Distance Field Resolution Scale
```

这会禁止为相应 StaticMesh 生成 Mesh Distance Field，但不关闭：

- StaticMesh 普通可见渲染；
- 物理碰撞；
- CARLA Actor 生命周期；
- SafeBench 评分和仿真推进；
- 常规相机、LiDAR 等 CARLA 传感器。

可能受影响的视觉功能包括 Distance Field AO、Ray Traced Distance Field Shadows 和依赖距离场的粒子碰撞。需要这些效果的关键资产不应直接批量关闭，而应走长期修复方案。

### 保守方案：仅处理高风险资产

如果必须保留大多数资产的距离场，可以把脚本的目标筛选条件改为明确的资产白名单，先处理上表中的 12 个百万面网格。但低面数不等于绝对安全，后续仍需根据日志补充名单。

### 长期方案

在 DCC 工具中执行以下操作后重新导入：

1. 减面并建立合理 LOD；
2. 删除退化、重复和零面积三角形；
3. 修复法线、切线和非流形拓扑；
4. 将接近 200 万面的整体网格拆分成多个空间上合理的 StaticMesh；
5. 重新启用距离场并逐个验证。

这比绕过引擎断言更可靠。不建议直接移除 UE4.26 的数组边界检查，因为那可能把明确崩溃变成静默内存破坏。

## 5. 批处理前置条件

工程已经启用了以下插件：

- `PythonScriptPlugin`
- `EditorScriptingUtilities`

运行脚本前必须临时关闭全局距离场生成，否则加载高风险资产时，后台任务可能在脚本修改属性之前再次崩溃。

1. 关闭 Unreal Editor。
2. 打开：

   ```text
   /home/fsm/Carla/carla/Unreal/CarlaUE4/Config/DefaultEngine.ini
   ```

3. 将：

   ```ini
   r.GenerateMeshDistanceFields=True
   ```

   临时改为：

   ```ini
   r.GenerateMeshDistanceFields=False
   ```

4. 重新启动 Unreal Editor：

   ```bash
   cd /home/fsm/Carla/carla
   make launch
   ```

脚本内也有安全检查：如果运行时检测到 `r.GenerateMeshDistanceFields` 仍然开启，会立即停止，不加载目标网格。

## 6. 运行批处理

脚本位置：

```text
/home/fsm/STF/SMap/STF/tools/tripo_distance_field_fix/disable_tripo_distance_fields.py
```

打开 Unreal Editor 的：

```text
Window -> Developer Tools -> Output Log
```

在命令框运行：

```text
py "/home/fsm/STF/SMap/STF/tools/tripo_distance_field_fix/disable_tripo_distance_fields.py"
```

也可以使用：

```text
File -> Execute Python Script
```

选择上述 Python 文件。

### 预演模式

修改脚本中的：

```python
DRY_RUN = True
```

该模式只列出目标和现有属性，不修改或保存 `.uasset`。应首先确认输出中的目标数量约为 137；资产目录后续发生变化时，实际数量可能不同。

### 正式处理

备份或提交相关 `.uasset` 后，将脚本改为：

```python
DRY_RUN = False
```

再次执行。脚本会：

1. 递归枚举资产目录；
2. 仅选择名称或路径包含 `tripo_node` 的资产；
3. 跳过非 `StaticMesh` 资产；
4. 将 LOD 0 的 `distance_field_resolution_scale` 设为 `0.0`；
5. 每处理一个资产就立即保存，避免中断后丢失全部进度；
6. 在 Output Log 中输出成功数、跳过数和失败列表。

注意：本目录中的脚本当前为 `DRY_RUN = False`。如果需要再次预演，应先手动改回 `True`。

## 7. 完成后的验证

1. 检查 Output Log 末尾，期望：

   ```text
   failed=0
   ```

2. 关闭 Editor。
3. 如果项目中的其他资产仍需要距离场，将 `DefaultEngine.ini` 恢复为：

   ```ini
   r.GenerateMeshDistanceFields=True
   ```

4. 重启 Editor，使全局配置生效。
5. 先打开两个已崩溃资产，再抽查其他百万面资产：

   ```text
   1a_tripo_node_2ad13da1_PropNode
   1a_tripo_node_26d632c4_PropNode
   ```

6. 确认不再出现 `GenerateSignedDistanceFieldVolumeData`、`TkDOPTree::Build` 或 `SplitTriangleList` 调用链崩溃。
7. 加载目标 CARLA 地图并运行一次 SafeBench 场景，确认视觉、碰撞、传感器和评分流程符合预期。

恢复全局 `r.GenerateMeshDistanceFields=True` 不会覆盖已经写入资产的 `Distance Field Resolution Scale = 0.0`。

## 8. 中断与回滚

脚本逐个保存资产，因此中途关闭或异常退出后可以重新运行；已经是 `0.0` 的资产会被跳过，处理过程具备幂等性。

回滚方式：

- 首选：从版本控制或备份恢复对应 `.uasset`；
- 或在 Static Mesh Editor 中把 `Distance Field Resolution Scale` 恢复为原值，通常为 `1.0`，再重新构建和保存；
- 批量恢复前仍应先全局关闭距离场，完成属性写入后再恢复全局配置并重启，避免高风险网格在恢复过程中立即触发原崩溃。

如果只需恢复少数关键资产，建议先完成减面和拓扑清理，再恢复其距离场生成。

## 9. 当前配置提醒

编写本文档时，项目配置仍为：

```ini
r.GenerateMeshDistanceFields=True
```

因此当前直接执行正式批处理脚本会触发脚本的安全停止。必须先修改配置并重启 Unreal Editor。
