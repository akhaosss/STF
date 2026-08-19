# 2.b 可运行场景定义

本目录随仓库发布，供使用者在不打开路线编辑器的情况下直接运行环形路口场景。

- 地图：`STF-2-b`
- 路线：一组已经审核并保存的 VUT、VT1、VT2 布置
- 场景数量：960
- 组合方式：120种天气 × 8组VT1/VT2车型
- 文件清单：`2b_scenario_manifest.json`

每个 `scenario_2b_*.json` 都是完整、独立的场景定义，包含路线、车辆位置、拓扑、门线、天气、车型和工程参数。运行器不需要读取编辑器拓扑缓存，也不会改写这些文件。

从仓库根目录启动CARLA并加载`STF-2-b`后，可运行仓库参考控制器示例：

```bash
./scripts/run_roundabout_behavior.sh
```

该命令默认遍历本目录中的全部场景。只想运行其中一部分时，应把所选JSON复制到单独的本地目录，并将`config/roundabout_2b.yaml`中的`runner.input_dir`指向该目录。

路线需要修改时才使用编辑器：

```bash
./scripts/start_roundabout_editor.sh
```

完整说明见[直接运行已有场景](../../../docs/scenarios/2b_roundabout/run_existing.md)。
