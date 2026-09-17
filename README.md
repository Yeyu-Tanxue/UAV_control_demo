# UAV Control Demo

这是轨道图像采集项目中的独立演示工程，用来验证一个尽量小、容易排查的视觉
控制闭环：

1. X500 起飞并悬停；
2. 在伴随计算机本地执行轨道分割并计算中心与航向；
3. 根据视觉误差低速前进、横移和修正偏航；
4. 再次悬停，重复若干轮后降落。

Spring YOLO 分割模型已经接入独立视觉状态机。活动 SITL 脚本不再使用固定
直线飞行；Gazebo 相机、YOLO 推理、几何计算和控制映射在同一任务进程完成。
真实树莓派入口使用 Picamera2，本地模型输出通过 MAVSDK 发送给 PX4。

最新的米制视觉闭环实验入口进一步加入相机内参、机体姿态、距轨面高度和动态
单应投影。在直轨 SITL 中，约 \(\pm0.4\) m、\(\pm10^\circ\) 的正反向初始误差
均完成收敛、三次低速前进脉冲和确认降落。结果见
[`docs/validation/metric-closed-loop-boundary-20260916.md`](docs/validation/metric-closed-loop-boundary-20260916.md)。

## 当前内容

- `src/uav_demo/mission.py`：与具体飞控解耦的任务状态机；
- `src/uav_demo/visual_mission.py`：不调用固定直线指令的视觉闭环状态机；
- `src/uav_demo/onboard_vision.py`：Gazebo/树莓派相机和本地 YOLO 推理；
- `src/uav_demo/vision_control.py`：掩膜中心线、航向与速度映射；
- `src/uav_demo/ground_projection.py`：姿态和高度驱动的动态轨面投影；
- `src/uav_demo/metric_rail_geometry.py`：鸟瞰图中的米制轨道中心与航向拟合；
- `src/uav_demo/metric_control.py`：米制误差到有界机体系速度的映射；
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

默认视觉任务起飞至 2 m，反复执行“悬停、本地三帧识别、短控制脉冲、停稳”，
然后退出 Offboard 并降落。SITL 后端必须显式传入 `--confirm-sitl`。

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

当前轻量工程测试共 53 项，覆盖任务状态迁移、识别拒绝和取消后的安全降落、
相机几何、动态投影、米制轨道拟合、控制限幅、Gazebo时间戳传输以及程序化轨道
世界生成。

## 进度报告

- [项目进度报告（PDF）](output/pdf/uav-rail-vision-progress-20260917.pdf)
- [LaTeX 源码](output/pdf/uav-rail-vision-progress-20260917.tex)
- [像素到鸟瞰米制映射说明（PDF）](output/pdf/image-to-birdseye-pixel-mapping.pdf)

## 安全边界

- 当前代码只用于 PX4/Gazebo 软件在环仿真；
- 识别失败、运行异常或取消时，任务请求零速度、退出 Offboard 并降落；
- 未确认触地时不会因超时而强制解锁；
- 真实飞行必须在封闭、停用、断电、无人员侵入且取得许可的场地进行，并保留 QGroundControl 监控和遥控人工接管。

## 数据和模型许可

仓库不直接提交训练数据、模型权重或第三方项目源码。数据来源、使用许可和高度核验记录位于 [`data/training-images/`](data/training-images/README.md)；引用第三方模型或数据时需保留原始署名和许可证。
