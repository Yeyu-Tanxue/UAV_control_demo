# 相似项目调研与复用建议

调研日期：2026-07-28；第二轮补充：2026-07-29

## 1. 调研目标

目标不是寻找一个可以整体搬运的大型无人机系统，而是为以下最小闭环寻找可靠的构件：

```text
PX4 起飞
  -> 悬停稳定
  -> 获取单帧
  -> CNN 分类完成
  -> 低速前飞固定时间或距离
  -> 速度归零并悬停
  -> 重复若干次
  -> 降落
```

筛选重点：

- 与 PX4、Gazebo Harmonic、MAVSDK-Python 兼容；
- 能在树莓派或普通 ARM Linux 上运行；
- 可以单帧、低频推理，不要求实时跟踪；
- 模块边界清楚，便于用假相机或假分类器做单元测试；
- 许可证明确，优先 BSD、MIT、Apache-2.0；
- 不为了一个简单 Demo 引入 ROS 2、SLAM、路径规划或完整地面站。

## 2. 核心结论

没有必要整体复刻任何一个第三方项目。最稳妥的组合是从五类项目中各取一个小构件：

| Demo 构件 | 首选参考 | 建议复用内容 |
|---|---|---|
| PX4 连接、解锁、降落、异常处理 | [MAVSDK-Python](https://github.com/mavlink/MAVSDK-Python) | 官方连接方式、Offboard 启停顺序、速度/位置设点和错误处理 |
| 仿真相机载体 | [PX4-gazebo-models](https://github.com/PX4/PX4-gazebo-models) | 直接使用 PX4 自带的带相机 X500 模型，不自制整套机模 |
| 树莓派相机读取 | [Picamera2](https://github.com/raspberrypi/picamera2) | `capture_array()` 和相机生命周期封装 |
| 轻量 CNN 分类 | [TensorFlow Lite Raspberry Pi 分类示例](https://github.com/tensorflow/examples/tree/master/lite/examples/image_classification/raspberry_pi) | EfficientNet-Lite0、预处理、单帧推理和 Top-K 结果格式 |
| 模块边界与安全门 | [PixEagle](https://github.com/alireza787b/PixEagle) | 相机、识别器、控制意图和真实飞控发布分离；识别失败不得触发前飞 |

这五项中，MAVSDK-Python、PX4-gazebo-models、Picamera2 和 TensorFlow Examples 都有明确的宽松许可证，可以作为优先阅读和后续小范围复用对象。PixEagle 也采用 Apache-2.0，但系统规模很大，只建议参考接口分层、安全闭锁和配置组织。

### 第二轮补搜结论

在排除首轮 16 个项目后，又筛出 8 个值得保留的仓库。新增项目中，真正贴近“识别事件触发下一段飞行”的有两个：

- [Intelligent-Quads/iq_gnc](https://github.com/Intelligent-Quads/iq_gnc)：示例任务会持续搜索，直到 YOLO 检测到人，再触发降落。飞控是 ArduPilot，但“感知发布事件，任务状态机决定动作”的结构与本 Demo 高度相似；
- [dji-sdk/Tello-Python](https://github.com/dji-sdk/Tello-Python)：官方示例把姿态识别结果绑定到飞行命令，证明“取帧—识别—离散动作”可以用很小的程序完成；但它基于 Python 2.7 和 Tello，只作流程参考。

另有两个项目特别适合校正状态机和模块边界：

- [Auterion/px4-ros2-interface-lib](https://github.com/Auterion/px4-ros2-interface-lib)：`Mode Executor` 本身就是“启动模式并等待完成”的状态机，且明确处理控制权移交和失效保护；
- [MikeS96/autonomous_landing_uav](https://github.com/MikeS96/autonomous_landing_uav)：把 Offboard、目标检测和控制器拆成三个 ROS 包，可参考感知与飞控之间的消息契约。

第二轮没有改变首选技术路线：第一版仍应使用 MAVSDK-Python + 单帧 TFLite 分类 + 小型显式状态机，不应为了复用上述项目而引入 ROS。

## 3. 建议保留的最小架构

```text
CameraSource
  capture() -> Frame

Classifier
  classify(Frame) -> ClassificationResult

FlightController
  takeoff()
  hold()
  move_forward(speed, duration)
  land()

DemoMission
  TAKEOFF
  STABILIZE
  CAPTURE
  CLASSIFY
  MOVE_FORWARD
  HOLD
  ...
  LAND
```

关键边界：

- `CameraSource` 同时支持仿真图像、树莓派相机和本地测试图片；
- `Classifier` 只返回结果，不直接控制无人机；
- `DemoMission` 只有收到“推理成功完成”事件后才允许进入 `MOVE_FORWARD`；
- 分类超时、相机无图、飞控断联或 Offboard 异常都进入 `HOLD` 或 `LAND`；
- 前飞指令必须有速度上限、持续时间上限和循环次数上限；
- 测试模式下使用假飞控，不能误连真实飞行器。

## 4. 优先复用清单

### A：后续实现时优先复用

1. **MAVSDK-Python 的 Offboard 示例**
   - 复用 `VelocityBodyYawspeed` 或 `PositionNedYaw` 的调用方式；
   - 复用“先发送零设点，再启动 Offboard”的顺序；
   - 不复制整个 SDK，仅把它作为依赖并参考官方示例。

2. **PX4 官方 Gazebo 相机模型**
   - 优先验证 `gz_x500_mono_cam`；
   - 若需要深度信息才考虑 `gz_x500_depth`；
   - 当前 Demo 只做 RGB 分类，不引入深度点云。

3. **TensorFlow Lite 分类示例**
   - 首选 EfficientNet-Lite0 224×224；
   - 只在悬停阶段处理单帧，无需持续视频推理；
   - 把模型加载放在任务启动阶段，避免每轮重复加载。

4. **Picamera2**
   - 封装为可替换的 `CameraSource`；
   - 真实相机接口与仿真/本地图片接口保持一致；
   - 不让相机异常直接穿透到飞行控制层。

### B：复用设计，不整体引入

1. **PixEagle**
   - 借鉴明确的数据流、控制意图和安全门；
   - 不引入 FastAPI、React 仪表盘、目标跟踪和完整插件系统。

2. **PX4-ROS2-Gazebo-YOLOv8**
   - 借鉴 Gazebo 相机主题、OpenCV 图像处理和带相机 X500 的组合；
   - 不引入它的 Docker、ROS 2、DDS、YOLO 实时检测和云台。

3. **AIRo Control Interface**
   - 借鉴有限状态机、命令超时、定位超时和安全空间参数；
   - 不引入 MPC、Acados、ROS Noetic 和自定义外环控制器。

4. **teNNo**
   - 借鉴“检测器可替换”和“确定性试验模式”；
   - 不使用 Tello 控制层、连续避障算法和旧版 YOLO/TensorFlow 配置。

5. **iq_gnc**
   - 借鉴“感知事件触发任务动作”和 ROS 订阅者向任务层传递检测结果；
   - 不引入 ArduPilot、MAVROS 和搜索救援任务本身。

6. **PX4 ROS 2 Interface Library**
   - 借鉴 `Mode Executor` 的异步完成回调、状态失败中止和控制权可被人工接管的原则；
   - 当前 Demo 不切换到 ROS 2/C++，只把这些原则落实到 Python 状态机。

7. **Autonomous Landing UAV**
   - 借鉴 `offboard / detector / controller` 三层拆分和检测结果经过明确消息契约再进入控制器；
   - 不复用降落 PID、旧 ROS 环境或特征点跟踪算法。

## 5. 明确不在第一版复用的内容

- ROS 2、MAVROS、Micro XRCE-DDS；
- SLAM、视觉里程计、轨迹规划、轨道中心线和避障；
- YOLO 实时目标检测、目标跟踪、云台跟随；
- FastAPI/React 地面站、远程视频服务；
- 多机编队、任务规划和搜索救援框架；
- IMX500、Coral、Jetson 等硬件加速器的专用代码；
- 第三方仓库中没有明确许可证的源码。
- 大型自主飞行框架的全量安装、子模块和行为树运行时。

这些能力不是永久排除，只是不属于“悬停—识别—前飞”的第一版 Demo。

## 6. 许可证规则

- 本目录的链接和分析不构成第三方源码再分发；
- BSD、MIT、Apache-2.0 项目仍需在复制代码时保留许可证和版权声明；
- `imx500-models` 中不同模型许可证不同，必须按具体模型核对；
- Ultralytics 主仓库为 AGPL-3.0/商业双轨，第一版不把其代码作为基础；
- 未提供许可证的项目只允许阅读和借鉴思路，不复制代码；
- 后续若增加 git submodule、vendor 目录或代码片段，必须单独做许可证复核。

## 7. 下一阶段建议

下一阶段仍然不需要完整飞行实现，建议只做三个可独立验证的薄接口：

1. 用本地图片运行一次 EfficientNet-Lite0 分类；
2. 用假飞控记录状态机是否按 `HOLD -> CLASSIFY -> MOVE -> HOLD` 转移；
3. 在 Gazebo 中确认带相机 X500 能输出一帧可读取图像。

三项分别通过后，再把它们接成完整 Demo。
