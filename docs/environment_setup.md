# 环境安装与验证

本文是当前根目录 `waypoints.py`、`run.py` 和 `scripts/` 的环境权威说明，面向第一次接触仓库的用户。当前验证基线为：

```text
操作系统：Ubuntu 22.04
Python：3.10
CARLA Server/Python API：0.9.16，二者必须匹配
Conda环境名：由使用者自行确定（下文示例使用stf-carla0916）
PyTorch/Torchvision：1.13.1 / 0.14.1
视频编码：FFmpeg + libx264
```

`TCP/README.md` 和 `TCP/environment.yml` 是上游旧版训练/Leaderboard环境，使用 CARLA 0.9.10.1与Python 3.7，不适用于本文的当前主流程。

## 1. 系统准备

最低准备内容：

- 64位 Linux 和可打开 Pygame/CARLA窗口的图形会话；
- Conda；
- CARLA 0.9.16 Server或当前机器的0.9.16源码构建；
- 与Python 3.10匹配的CARLA 0.9.16 wheel；
- FFmpeg并启用H.264编码；
- 仅在使用仓库TCP示例时准备对应checkpoint；
- TCP实时运行建议使用可用的NVIDIA GPU/CUDA。

编辑器和behavior ADS不要求CUDA。TCP代码可以回退CPU，但可能无法满足实时实验要求；是否强制CUDA由 `config/roundabout_2b.yaml` 的 `ads.tcp.require_cuda` 控制。

## 2. 创建 Conda 环境

已有满足Python和CARLA版本要求的环境时，可使用原环境并跳到“安装和核对依赖”。以下命令创建一个示例环境；`stf-carla0916`只是示例名称，不是仓库或开发者机器上的固定环境：

```bash
conda create -n stf-carla0916 python=3.10 pip -y
conda activate stf-carla0916
```

确认没有误用其他Python：

```bash
which python
python --version
```

输出应指向刚才激活环境中的Python，版本应为3.10.x。

统一配置中的`environment.conda_env`默认留空，此时启动脚本使用当前终端已激活的Python环境。若希望无需预先激活、由脚本自动选择环境，可在本机把它改成实际环境名，例如：

```yaml
environment:
  conda_env: stf-carla0916
```

该值属于本机运行配置，不应在公共分支中提交个人环境名称。

## 3. 安装和核对依赖

在仓库根目录执行：

```bash
python -m pip install -r environment/requirements.txt
```

若需要特定CUDA版本，应先按机器驱动安装对应的PyTorch/Torchvision wheel，再安装requirements；已安装的兼容版本会被保留或按约束核对。兼容性参考组合为Torch 1.13.1 + CUDA 11.7，但GPU是否可用仍取决于主机驱动和运行容器。

不建议执行 `pip install -r good_env.txt`：该文件包含ROS、Autoware和整机级依赖，不是项目最小环境。

## 4. 安装匹配的 CARLA Python API

先确认本机CARLA根目录，以下用`<CARLA_ROOT>`表示。

其中应存在：

```text
PythonAPI/carla/dist/carla-0.9.16-cp310-...whl
PythonAPI/carla/agents/navigation/
```

安装与Python 3.10匹配的wheel，文件名以实际构建产物为准：

```bash
conda activate stf-carla0916
python -m pip install /path/to/CARLA/PythonAPI/carla/dist/carla-0.9.16-cp310-cp310-linux_x86_64.whl
```

记录CARLA根目录，使本仓库脚本能够自动找到 `agents.navigation`：

```bash
conda env config vars set -n stf-carla0916 CARLA_UE4_ROOT=/path/to/CARLA
conda deactivate
conda activate stf-carla0916
```

也可以直接在 [环岛统一配置](../config/roundabout_2b.yaml) 的 `environment.carla_root` 中填写绝对路径。

不要只安装 `carla` wheel而忽略 `PythonAPI/carla/agents`。wheel提供客户端模块，GlobalRoutePlanner等导航代码仍来自CARLA源码/发行目录。

## 5. 安装 FFmpeg

推荐在Conda环境安装：

```bash
conda install -n stf-carla0916 -c conda-forge ffmpeg -y
```

检查H.264编码：

```bash
conda run -n stf-carla0916 ffmpeg -version
```

输出配置应包含 `--enable-libx264`，否则 `run.py` 可能无法生成MP4。

## 6. 可选：准备TCP checkpoint

只有运行仓库TCP接入示例时才需要checkpoint，并在统一YAML中填写：

```yaml
ads:
  tcp:
    model_path: /absolute/path/to/best_model.ckpt
    require_cuda: true
```

仓库中的 `TCP/roach/log/ckpt_11833344.pth` 不是默认TCP `best_model.ckpt`，不能因为扩展名相似而直接替代。

## 7. 执行环境自检

从仓库根目录运行：

```bash
./scripts/check_environment.sh
```

自检项目包括：

- Conda环境与Python版本；
- CARLA 0.9.16 Python包；
- Pygame、NumPy、Pandas、ImageIO、PyYAML、Pillow、Torch和Torchvision；
- `agents.navigation.GlobalRoutePlanner`；
- FFmpeg/libx264和实际MP4写入；
- CUDA状态；
- 可选TCP checkpoint；
- CARLA Server连接、客户端/服务端版本和地图名称。

CARLA Server未启动时，环境检查会把连接标为警告。未配置TCP checkpoint只表示TCP示例不可用，不阻止编辑器或Behavior参考控制器运行；配置了无效checkpoint时仍会报错。

## 8. 启动 CARLA Server

CARLA源码/UE4Editor构建可使用：

```bash
conda activate stf-carla0916
cd <CARLA_ROOT>
./CarlaUE4-with-coredump.sh -windowed -benchmark -fps=20 -carla-port=2000
```

官方打包版通常使用其自带的 `CarlaUE4.sh`。无论哪种方式，端口必须与场景YAML或运行命令一致。

## 9. 第一次运行

仓库已经包含可运行的环岛2.b场景定义。CARLA加载`STF-2-b`后，可直接运行参考控制器：

```bash
./scripts/run_roundabout_behavior.sh
```

只运行部分场景、结果位置和ADS接入边界见[直接运行已有场景](scenarios/2b_roundabout/run_existing.md)。需要修改路线时再使用`./scripts/start_roundabout_editor.sh`，完整编辑流程见[环岛编辑与扩展](scenarios/2b_roundabout/startup.md)。

信号灯1.d见 [机动车信号灯场景](scenarios/1d_motor_vehicle_signal/README.md)。其他场景见 [通用编辑器与运行器](README.md)。

## 10. 常见问题

### `ModuleNotFoundError: carla`

确认当前Python属于你为本项目准备的环境，并重新安装匹配wheel。不要混用系统Python、用户目录中的不同CARLA版本和Conda版本。

### `ModuleNotFoundError: agents`

确认 `CARLA_UE4_ROOT/PythonAPI/carla/agents/navigation` 存在。主项目启动脚本会自动把 `PythonAPI/carla` 加入子进程路径。

### CARLA连接超时

检查Server是否完全启动、端口是否为2000，以及防火墙/容器网络。根目录 `run.py` 现在支持配置host/port，环岛脚本从统一YAML读取。

### 客户端和服务端版本不一致

必须用同一CARLA构建的wheel和Server。版本不一致可能在Actor、地图、传感器或同步模式调用时产生隐蔽错误。

### TCP只能使用CPU

执行：

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
```

若要求实时GPU实验，应先修复显卡驱动、CUDA和PyTorch wheel，再把YAML中的 `require_cuda` 设为true。

### 包来自 `~/.local` 而非Conda环境

这会降低可移植性。可用以下命令确认包位置：

```bash
python -m pip show pygame numpy torch torchvision
```

新机器应把依赖实际安装到目标Conda环境，不要依赖旧用户目录的包。
