# 场景专项文档索引

场景专项文档统一使用 `docs/scenarios/<场景编号_名称>/`。每个目录的 `README.md` 是场景定义入口；启动、配置、实验方法、图片和其他补充材料也保存在同一目录。

| 场景 | 定义入口 | 补充文档 | 状态 |
|---|---|---|---|
| 1.d 机动车信号灯 | [1d_motor_vehicle_signal/README.md](1d_motor_vehicle_signal/README.md) | — | 专项实现 |
| 2.b 环形路口 | [2b_roundabout/README.md](2b_roundabout/README.md) | [直接运行已有场景](2b_roundabout/run_existing.md)、[编辑与扩展](2b_roundabout/startup.md)、[参数、证据与结果目录](2b_roundabout/results_and_parameters.md) | 含可运行场景数据 |

当前目录根部的其他PNG是通用手册引用的历史场景示意资产，尚无独立专项Markdown。以后为某一场景增加定义或操作文档时，应先创建对应子目录，并把该场景的文档和资产一并归档到其中，不再把场景Markdown直接放到 `docs/` 或 `docs/scenarios/` 根部。

通用操作见 [docs/README.md](../README.md)，仓库全部文档关系见 [根README](../../README.md)。
