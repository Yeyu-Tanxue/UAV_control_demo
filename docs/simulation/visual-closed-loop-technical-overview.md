# 基于视觉的无人机铁轨循迹仿真技术文档

## 1. 文档目的与当前状态

本文档说明 `UAV_control_demo` 中“悬停—识别—飞行—悬停”视觉闭环 Demo 的
系统架构、关键模块、算法、安全机制、结果输出，以及向实体树莓派和 PX4 迁移时
需要完成的工作。

当前系统已完成三周期 SITL 闭环验证。YOLO 分割、轨道中心线计算和控制量生成均在
WSL 内同一个 Python 进程中真实执行；Gazebo 只替代真实相机和飞行器物理环境，
PX4 SITL 替代实体飞控。

## 2. 总体架构

```text
Gazebo 铁轨世界
    ↓ 640×480，5 FPS
Gazebo 单目相机 → /tmp/uav_demo_camera
    ↓
Spring YOLO 分割模型（WSL 本地 CPU）
    ↓
轨道掩膜 → 左右包络 → 中心点 → 中心线拟合
    ↓
横向偏差 + 图像航向偏差
    ↓
前向速度 + 横向速度 + 偏航速度
    ↓
MAVSDK Offboard → PX4 SITL → Gazebo X500
```

计划中的实机链路为：

```text
树莓派 CSI 相机 → 树莓派本地 YOLO/NCNN
    → 同一套几何和控制映射
    → MAVSDK 串口 → 实体 PX4
```

地面计算机只负责 QGroundControl 监控、日志和人工接管，不参与实机识别决策。

## 3. 关键模块

| 模块 | 职责 |
|---|---|
| `scripts/start_realistic_rail_sitl.sh` | 启动铁轨世界、Gazebo Server 和 PX4 SITL |
| `simulation/gazebo/worlds/rail_demo_realistic.sdf` | 定义直轨、地面、光照和起飞区 |
| `simulation/gazebo/models/x500_mono_cam/model.sdf` | 将俯视相机固定到 X500 |
| `simulation/gazebo/models/mono_cam/model.sdf` | 定义相机参数和图片输出路径 |
| `scripts/run_sitl_demo.sh` | 启动视觉闭环并生成结果图 |
| `src/uav_demo/onboard_cli.py` | 参数解析和模块装配 |
| `src/uav_demo/onboard_vision.py` | 图像源、YOLO、三帧融合、记录 |
| `src/uav_demo/vision_control.py` | 掩膜几何、中心线和控制映射 |
| `src/uav_demo/visual_mission.py` | 任务状态机和异常处理 |
| `src/uav_demo/backends/mavsdk_px4.py` | PX4 连接、起飞、速度和降落 |
| `src/uav_demo/interfaces.py` | 识别器与飞控后端公共接口 |
| `scripts/render_visual_decisions.py` | 渲染最近三周期的可视化结果 |

接口层把算法与硬件分离。仿真使用 `GazeboSpoolFrameSource`，树莓派使用
`Picamera2FrameSource`，后续算法接收的都是 OpenCV BGR 图像。

## 4. Gazebo 与 PX4 SITL

入口为 [`start_realistic_rail_sitl.sh`](../../scripts/start_realistic_rail_sitl.sh)。脚本
设置项目内 Gazebo 资源路径，并指定：

```bash
PX4_GZ_STANDALONE=1
PX4_GZ_WORLD=rail_demo_realistic
PX4_GZ_MODEL_POSE=-16.85,0,0.2,0,0,0
```

随后启动：

```bash
gz sim -r -s simulation/gazebo/worlds/rail_demo_realistic.sdf
make px4_sitl gz_x500_mono_cam
```

[`rail_demo_realistic.sdf`](../../simulation/gazebo/worlds/rail_demo_realistic.sdf) 使用
8 段 4 m 直轨，总长约 32 m。轨道中心的世界 X 坐标依次为
`-14、-10、-6、-2、2、6、10、14 m`。无人机生成在 `(-16.85, 0, 0.2)`，机头
沿轨道的世界 `+X` 方向。当前世界不包含弯轨、岔道、积雪和复杂背景。

[`mono_cam/model.sdf`](../../simulation/gazebo/models/mono_cam/model.sdf) 设置：

- 分辨率 640×480；
- 水平视场角约 110°；
- 更新频率 5 FPS；
- 裁剪范围 0.1～200 m；
- 帧目录 `/tmp/uav_demo_camera`。

[`x500_mono_cam/model.sdf`](../../simulation/gazebo/models/x500_mono_cam/model.sdf)
将相机固定在机体 `(0.12, 0, 0.18)`，俯角约 35°；飞行动力学仍使用 PX4 标准
X500。

## 5. 任务入口与参数

运行：

```bash
./scripts/run_sitl_demo.sh --control-steps 3
```

[`run_sitl_demo.sh`](../../scripts/run_sitl_demo.sh) 固定使用 MAVSDK、Gazebo 图像源、
Spring 分割模型和 CPU 推理，不再调用旧的定时直飞任务。

[`onboard_cli.py`](../../src/uav_demo/onboard_cli.py) 依次构造图像源、检测器、融合
识别器、PX4 后端和任务状态机。主要默认参数为：

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `imgsz` | 640 | YOLO 输入尺寸 |
| `confidence` | 0.15 | 置信度阈值 |
| `frames-per-decision` | 3 | 每次决策图像数 |
| `min-valid-frames` | 2 | 最少有效帧数 |
| `takeoff-altitude` | 2.0 m | 起飞高度 |
| `forward-speed` | 0.12 m/s | 最大前进速度 |
| `command-duration` | 0.75 s | 单次速度脉冲时长 |
| `settle-time` | 0.50 s | 运动后稳定时间 |
| `max-consecutive-misses` | 3 | 安全降落前允许的连续失败数 |

## 6. 图像采集与 YOLO

[`GazeboSpoolFrameSource`](../../src/uav_demo/onboard_vision.py) 读取修改时间最新且未处理
的图像。Gazebo 可能产生“文件已出现但 PNG 尚未写完”的短暂状态，因此读取器只有
在 OpenCV 成功解码后才消费该帧；失败时每 50 ms 重试，最多等待 3 s。

实机对应的 `Picamera2FrameSource` 配置 640×480、BGR888，通过
`camera.capture_array("main")` 直接获取 CSI 画面，不需要先写入磁盘。

`LocalYoloRailDetector` 运行：

```python
model.predict(
    source=frame.image,
    imgsz=640,
    conf=0.15,
    device="cpu",
    max_det=3,
)
```

控制算法使用 `result.masks.data` 中的像素级分割掩膜。YOLO 外接框只提供置信度等
信息，不使用框的左右坐标计算飞行方向。最佳候选按下式选择：

```text
score = confidence × (0.5 + 0.5 × geometry_quality)
```

## 7. 掩膜到中心线

核心为 [`RailMaskGeometry`](../../src/uav_demo/vision_control.py)。

### 7.1 扫描区域

只处理图像高度 50%～88%，并设置 28 条水平扫描线。顶部容易出现远场伪掩膜，
最底部可能受到起飞坪、视野截断和畸变影响。

### 7.2 左右包络

每条扫描线寻找长度不少于 3 像素的连续掩膜段，忽略中心落在图像横向 8%～92%
以外的边缘片段，然后计算：

```text
x_left(y)   = 所有有效片段的最左像素
x_right(y)  = 所有有效片段的最右像素
x_center(y) = [x_left(y) + x_right(y)] / 2
```

Spring 模型可能把枕木和左右钢轨分成多个区域，因此使用整体掩膜包络，而不是单个
连通块，更不是 YOLO 框中心。

### 7.3 透视和拟合

正常前视直轨应近宽远窄。从近向远扫描时，如果远处归一化宽度比上一有效行突然
增加超过 0.04，则丢弃该行。少于 12 条有效行时拒绝整个掩膜。

算法拟合 `x(y)=ky+b`，并依据残差和中位数绝对偏差进行两轮异常点剔除。近点取
有效 Y 坐标 85% 分位，远点取 20% 分位。

### 7.4 横向和航向误差

横向误差：

```math
e_l = \frac{x_{near}-0.5}{0.5}
```

`e_l=0` 表示轨道在画面中心，正值表示轨道在右侧，负值表示轨道在左侧。

图像航向误差：

```math
e_\psi=\operatorname{atan2}((x_{far}-x_{near})W,(y_{near}-y_{far})H)
```

远点位于近点右侧时为正。当前横向值仍是归一化像素误差，航向值也是图像角度，
尚未通过相机标定转换为严格的轨道平面距离和世界航向角。

## 8. 三帧融合

[`OnboardRailRecognizer`](../../src/uav_demo/onboard_vision.py) 默认获取 3 张新图，至少
2 张同时通过模型和几何检查才接受一次决策。对置信度、横向偏差、航向偏差和有效
扫描行数取中位数，以降低单帧抖动和误检。

结果由 [`RecognitionResult`](../../src/uav_demo/interfaces.py) 表示。有效帧不足时返回
`rail_not_stable`，任务立即保持零速度，且不复用上一周期控制命令。

## 9. 视觉到控制映射

[`map_estimate_to_command`](../../src/uav_demo/vision_control.py) 输出前向、向右和偏航
速度。前向速度按误差自动衰减：

```math
s_l=|e_l|/0.50,\quad s_\psi=|e_\psi|/20^\circ
```

```math
v_f=0.12\operatorname{clamp}(1-\max(s_l,s_\psi),0,1)
```

横向和偏航速度为：

```math
v_r=\operatorname{clamp}(0.16e_l,-0.10,0.10)
```

```math
\dot\psi=\operatorname{clamp}(0.35e_\psi+3.0e_l,-8,8)
```

横向误差达到 0.50 或航向误差达到 20° 时，前进速度降为零，只执行对正。

## 10. 任务状态机

[`VisualMissionRunner`](../../src/uav_demo/visual_mission.py) 的状态顺序为：

```text
IDLE → CONNECTING → TAKING_OFF
     → HOVERING → RECOGNIZING → APPLYING_VISION_COMMAND
     → HOVERING → 下一周期
     → LANDING → COMPLETE
```

每周期先零速度悬停，识别 3 帧，融合误差，执行 0.75 s 视觉速度脉冲，然后立即
恢复零速度并稳定 0.50 s。所有运动命令都来自本周期视觉结果。

## 11. MAVSDK/PX4 后端

[`MavsdkPx4Controller`](../../src/uav_demo/backends/mavsdk_px4.py) 在 SITL 中连接
`udpin://0.0.0.0:14540`，等待系统、全局位置和 Home 有效后解锁起飞。进入 Offboard
前先发送零速度设定值。

视觉命令使用：

```python
VelocityBodyYawspeed(forward_m_s, right_m_s, 0.0, yaw_rate_deg_s)
```

向下速度固定为零，因此视觉负责前后、左右和偏航，高度由 PX4 保持。

## 12. 安全机制

- 无 `--confirm-sitl` 或 `--confirm-flight` 时禁止 MAVSDK 后端运行；
- 模型或图像目录不存在时不启动；
- 有效帧不足时保持零速度；
- 不复用上一周期命令；
- 连续 3 次识别失败触发 `VisionLost`；
- 任意未处理异常进入 `safe_stop_and_land()`；
- 安全流程依次尝试零速度、停止 Offboard、发送 Land；
- 降落遥测超时时不会盲目在空中强制解锁。

实机首次测试必须拆桨或固定机架，确认前后、左右和偏航符号。之后只能在封闭、停用、
断电、无人员侵入且允许试飞的场地进行，并保留遥控器与 QGroundControl 人工接管。

## 13. 结果记录与可视化

实时数值写入：

```text
captures/visual_control/<时间戳>/decisions.jsonl
```

试飞结束后，[`render_visual_decisions.py`](../../scripts/render_visual_decisions.py) 为最近
三个周期生成原图、二值掩膜、叠加图和 `summary.json`。叠加图中绿色为分割掩膜，
红线为轨道中心方向，白线为画面中心，蓝/黄点为远/近中心。

最近一次三周期结果位于 `captures/visual_control/20260909_001059/`：

| 周期 | 置信度 | 横向偏差 | 航向偏差 | 前进 | 横向 | 偏航 |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 0.363 | +0.002 | +1.04° | 0.114 m/s | +0.000 m/s | +0.37°/s |
| 2 | 0.717 | +0.000 | +2.08° | 0.107 m/s | +0.000 m/s | +0.73°/s |
| 3 | 0.767 | -0.030 | +4.28° | 0.094 m/s | -0.005 m/s | +1.41°/s |

三周期均完成识别、视觉控制和自动降落，证明活动脚本执行的是视觉反馈控制而非固定
速度直飞。

## 14. 树莓派迁移

```bash
./scripts/setup_rpi_vision.sh
export RAIL_MODEL="$PWD/models/rail_spring_ncnn_model"
export PX4_ADDRESS="serial:///dev/ttyAMA0:921600"
./scripts/run_rpi_vision_demo.sh --control-steps 3
```

迁移关系：Gazebo PNG 换为 Picamera2 CSI；`.pt`/x86 CPU 优先换为 NCNN/ARM CPU；
UDP 换为 UART；PX4 SITL 换为实体 PX4。优先使用 64 位 Raspberry Pi OS 和树莓派 5。

## 15. 当前局限与后续工作

当前版本证明了视觉闭环链路，但还不是可靠工程循迹系统：

1. 横向误差尚未换算成实际米，航向角也不是严格的世界坐标角；
2. 相机内参、畸变和机体外参尚未标定；
3. 当前几何假设单条直轨，不能直接处理弯道和道岔；
4. 人员检测尚未并入统一安全决策；
5. 当前是有界比例映射，没有 PID、状态估计或预测控制；
6. 高度完全依赖 PX4，视觉不估计高度；
7. 简单世界不能覆盖冰雪、阴影、遮挡和反光；
8. 树莓派推理延迟、温度、曝光和串口可靠性尚未实测。

建议依次完成：NCNN 导出和树莓派测速、Picamera2 验证、拆桨串口与方向测试、相机
标定、像素到实际距离映射、Gazebo 初始偏差收敛测试、弯道/道岔处理、人员检测安全
融合，最后再进行低高度低速度实飞。

## 16. 测试状态

当前 7 项视觉几何和任务安全单元测试已通过，覆盖居中直轨、顶部伪掩膜、轨道方向、
对准前进、大误差停车、视觉命令来源和连续识别失败安全降落。单元测试不能替代相机
标定、硬件在环测试和实机安全测试。
