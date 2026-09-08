# UAV Control Demo

这是轨道图像采集项目中的独立演示工程，用来验证一个尽量小、容易排查的任务闭环：

1. X500 起飞并悬停；
2. 执行一次识别；
3. 低速向前飞行一小段；
4. 再次悬停，重复若干轮后降落。

目前识别结果仍由模拟器产生。Gazebo 相机和真实模型尚未接入任务状态机，因此本仓库当前用于验证飞行流程、接口拆分和异常处理，不代表视觉闭环已经完成。

## 当前内容

- `src/uav_demo/mission.py`：与具体飞控解耦的任务状态机；
- `src/uav_demo/backends/`：dry-run 后端和 MAVSDK/PX4 SITL 后端；
- `simulation/gazebo/`：程序化生成的 30 m 标准轨距简化轨道场景；
- `tools/`：轨道数据审计、YOLO 格式转换、预标注和训练入口；
- `docs/vision/`：轨道区域分割、道岔检测和人工复核记录；
- `tests/`：状态机、数据转换和仿真场景测试。

## 快速检查

环境要求为 Ubuntu 22.04、PX4 v1.17.0、Gazebo Harmonic、Python 3.10 和 MAVSDK-Python 3.15.3。

不连接飞控时运行：

```bash
./scripts/setup_python.sh
./scripts/run_dry_demo.sh
```

启动普通 X500 SITL：

```bash
./scripts/start_px4_sitl.sh
```

启动程序化轨道场景：

```bash
./scripts/start_rail_sitl.sh
```

在另一个终端运行任务：

```bash
./scripts/run_sitl_demo.sh
```

默认任务起飞至 2 m，完成两轮“悬停、模拟识别、0.2 m/s 前飞 0.5 m、停稳”，然后退出 Offboard 并降落。SITL 后端必须显式传入 `--confirm-sitl`。

详细启动和异常处理见 [`docs/simulation/README.md`](docs/simulation/README.md)。

## 已有数据与视觉工作

- RailGoerl24：审计 12,205 帧、61 段视频和 33,853 个目标实例，并按完整视频划分数据集；
- L4R_NLB：整理春、秋、冬三季轨道区域分割样本和多季节道岔检测样本；
- 轨道分割：完成单季节 YOLO 分割基线和 RailGoerl24 跨域预标注；
- 道岔检测：将方向相关的 `fork/merge` 合并为单一 `switch` 类，模型目前只用于人工筛选和预标注。

具体数据口径、训练配置和限制见 [`docs/vision/`](docs/vision/)。训练图像、模型权重、运行日志和训练输出不进入普通 Git 历史。

## 测试

在仓库根目录运行：

```bash
PYTHONPATH="$PWD:$PWD/src" python -m unittest discover -s tests -v
```

当前轻量工程测试共 18 项，覆盖任务状态迁移、识别拒绝和取消后的安全降落、数据转换、序列级划分以及程序化轨道世界生成。

## 安全边界

- 当前代码只用于 PX4/Gazebo 软件在环仿真；
- 识别失败、运行异常或取消时，任务请求零速度、退出 Offboard 并降落；
- 未确认触地时不会因超时而强制解锁；
- 真实飞行必须在封闭、停用、断电、无人员侵入且取得许可的场地进行，并保留 QGroundControl 监控和遥控人工接管。

## 数据和模型许可

仓库不直接提交训练数据、模型权重或第三方项目源码。数据来源、使用许可和高度核验记录位于 [`data/training-images/`](data/training-images/README.md)；引用第三方模型或数据时需保留原始署名和许可证。