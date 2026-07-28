# 相似项目逐项笔记

下面的“复用”是针对简单 Demo 的判断，不代表对原项目总体质量的评价。

## A. 高优先级：可以直接支撑 Demo

### 1. MAVSDK-Python

- 项目：[mavlink/MAVSDK-Python](https://github.com/mavlink/MAVSDK-Python)
- 技术：Python、asyncio、MAVSDK、MAVLink、PX4
- 许可证：BSD-3-Clause
- 相关内容：
  - `examples/offboard_velocity_body.py`
  - `examples/offboard_position_ned.py`
  - `examples/takeoff_and_land.py`
- 值得复用：
  - PX4 连接和健康状态等待；
  - Offboard 启动前发送初始设点；
  - 机体系前向速度和局部 NED 位置设点；
  - `OffboardError` 处理及安全降落流程。
- 不照搬：
  - 示例中的大速度和长时间动作；
  - 缺少超时和完整任务状态记录的演示式代码。
- 结论：**飞行控制唯一首选基础**。当前目标本来就适合低带宽、低频指令，没必要换 ROS 2。

### 2. PX4 Gazebo Models

- 项目：[PX4/PX4-gazebo-models](https://github.com/PX4/PX4-gazebo-models)
- 技术：Gazebo、SDF、PX4 仿真模型
- 许可证：BSD-3-Clause
- 相关模型：`x500_mono_cam`、`x500_depth`、`x500_gimbal`
- 值得复用：
  - 官方维护的相机传感器配置；
  - 与 PX4 SITL 匹配的 X500 模型；
  - 仿真世界和资源加载方式。
- 不照搬：
  - 第一版不修改云台和深度相机模型；
  - 不复制整个模型仓库到 Demo。
- 结论：**仿真相机首选**。直接选官方带相机机型比维护自定义 SDF 更稳妥。

### 3. TensorFlow Lite Raspberry Pi Image Classification

- 项目：[tensorflow/examples：Raspberry Pi 图像分类](https://github.com/tensorflow/examples/tree/master/lite/examples/image_classification/raspberry_pi)
- 技术：Python、TFLite、EfficientNet-Lite0、Pi Camera/USB Camera
- 许可证：Apache-2.0
- 相关文件：`classify.py`、`requirements.txt`、`setup.sh`
- 值得复用：
  - 小型 `tflite_runtime`，避免安装完整 TensorFlow；
  - EfficientNet-Lite0 默认模型；
  - 预处理、标签、Top-K 结果和推理计时；
  - 摄像头帧到分类结果的最小闭环。
- 不照搬：
  - 实时显示循环；
  - 第一版不接 Coral USB Accelerator。
- 结论：**CNN 分类首选参考**。比 YOLO 更符合“识别完成再飞”的低频 Demo。

### 4. Picamera2

- 项目：[raspberrypi/picamera2](https://github.com/raspberrypi/picamera2)
- 技术：Python、libcamera、树莓派 CSI 相机
- 许可证：BSD-2-Clause
- 值得复用：
  - `capture_array()` 单帧接口；
  - 相机配置、启动、停止和元数据读取；
  - Raspberry Pi OS 上的标准相机栈。
- 不照搬：
  - GUI、Qt 应用、编码和复杂视频管线；
  - 仿真环境不依赖 Picamera2。
- 结论：**实机相机后端首选**，但必须放在抽象接口后面。

### 5. PixEagle

- 项目：[alireza787b/PixEagle](https://github.com/alireza787b/PixEagle)
- 技术：PX4、MAVSDK、OpenCV、YOLO、GStreamer、FastAPI、React
- 许可证：Apache-2.0
- 值得复用：
  - `camera -> preprocess -> detector/tracker -> command intent -> safety gate -> PX4 publisher` 的显式数据流；
  - 本地测试路径和真实飞控发布路径隔离；
  - 相机、检测器、跟随器的工厂/接口模式；
  - 配置校验、失效闭锁和仿真不等于实机合格的安全原则。
- 不照搬：
  - Web 仪表盘、用户系统、远程流媒体；
  - 目标跟踪、跟随算法和插件框架全量实现；
  - 安装器和服务管理系统。
- 结论：**架构参考价值极高，代码整体引入价值低**。

### 6. PX4 ROS 2 Beginner Tutorials

- 项目：[sidharthmohannair/px4-ros2-beginner-tutorials](https://github.com/sidharthmohannair/px4-ros2-beginner-tutorials)
- 技术：PX4、Gazebo Harmonic、ROS 2 Humble、OpenCV
- 许可证：MIT
- 值得复用：
  - 查找 Gazebo 相机主题；
  - 将 Gazebo 图像转换成 OpenCV 数组；
  - 相机模型和仿真桥接的排错步骤。
- 不照搬：
  - ROS 2 节点、`cv_bridge` 和 DDS 依赖；
  - 文档规划中尚未实现的部分。
- 结论：**只把它当相机链路说明书**。

## B. 中优先级：局部设计值得借鉴

### 7. PX4-ROS2-Gazebo-YOLOv8

- 项目：[monemati/PX4-ROS2-Gazebo-YOLOv8](https://github.com/monemati/PX4-ROS2-Gazebo-YOLOv8)
- 技术：PX4、Gazebo、ROS 2、MAVSDK、OpenCV、YOLOv8、Docker
- 许可证：仓库根目录未见明确许可证，按“不可复制源码”处理
- 值得借鉴：
  - 相机版 X500、Gazebo 图像、OpenCV 推理和 MAVSDK 控制能够共存；
  - `uav_camera_det.py` 展示了图像主题到模型推理的最短路径；
  - 仿真中放置可识别目标的方法。
- 不复用：
  - 第三方源码；
  - Docker GPU、六终端启动、云台和实时 YOLO。
- 结论：**最像目标 Demo 的外观，但不是最适合直接复用的代码库**。

### 8. Jaeyoung-Lim/px4-offboard

- 项目：[Jaeyoung-Lim/px4-offboard](https://github.com/Jaeyoung-Lim/px4-offboard)
- 技术：ROS 2、Python、PX4、Micro XRCE-DDS
- 许可证：BSD-3-Clause
- 值得复用：
  - Python 位置设点控制的组织方式；
  - 仿真与伴随计算机启动配置分离；
  - 可视化和控制节点分离。
- 不照搬：
  - ROS 2 工作区和 Micro XRCE Agent；
  - 对本 Demo 多余的 RViz 轨迹可视化。
- 结论：**作为 MAVSDK 官方示例的补充阅读，不作为依赖**。

### 9. Clover

- 项目：[CopterExpress/clover](https://github.com/CopterExpress/clover)
- 技术：PX4、树莓派4、ROS Noetic、MAVROS、OpenCV、相机
- 许可证：源码 MIT；文档 CC BY-NC-SA 4.0
- 值得借鉴：
  - 飞控与伴随计算机的硬件分工；
  - 树莓派镜像、网络、相机和 PX4 的部署清单；
  - 教学无人机的低门槛工作流。
- 不照搬：
  - 老版 ROS/MAVROS 软件栈；
  - 整张预配置系统镜像。
- 结论：**实机部署清单有用，软件架构不迁移**。

### 10. teNNo

- 项目：[williamcorsel/teNNo](https://github.com/williamcorsel/teNNo)
- 技术：Python、Tello、OpenCV、SIFT、YOLOv4、TensorFlow、EfficientDet
- 许可证：Apache-2.0
- 值得借鉴：
  - 检测器后端可以替换；
  - 试验模式、日志和动作结果确认；
  - 检测与飞行控制在同一任务中的事件衔接。
- 不照搬：
  - Tello 控制协议；
  - 基于目标尺寸变化的避障逻辑；
  - 旧版模型依赖和连续视频推理。
- 结论：**适合借鉴测试模式，不适合借鉴飞控实现**。

### 11. AIRo Control Interface

- 项目：[HKPolyU-UAV/airo_control_interface](https://github.com/HKPolyU-UAV/airo_control_interface)
- 技术：PX4、ROS Noetic、MAVROS、MPC、Acados、FSM
- 许可证：仓库页面未明确显示，按“只借鉴设计”处理
- 值得借鉴：
  - `RC_MANUAL -> AUTO_TAKEOFF -> AUTO_HOVER -> POS_COMMAND -> AUTO_LAND` 状态划分；
  - 状态、遥控、里程计和命令超时；
  - 安全空间、速度和偏航速率限制；
  - 外部命令停止时回到悬停。
- 不复用：
  - MPC、Acados 和自定义外环控制器；
  - ROS Noetic/MAVROS 代码。
- 结论：**状态机和超时设计很有价值，系统本身过重**。

### 12. Raspberry Pi IMX500 Model Zoo

- 项目：[raspberrypi/imx500-models](https://github.com/raspberrypi/imx500-models)
- 技术：IMX500 AI Camera、EfficientNet、MobileNet、YOLO、SSD
- 许可证：按模型分别授权，不能统一处理
- 值得借鉴：
  - 224×224 分类模型候选；
  - EfficientNet-Lite0、MobileNetV2 等边缘模型比较；
  - 分类、检测和分割任务的硬件端示例入口。
- 不照搬：
  - 第一版不购买或绑定 IMX500；
  - 未核对单个模型许可证前不复制模型文件。
- 结论：**未来硬件加速候选，不是当前依赖**。

## C. 低优先级：只保留背景材料

### 13. PX4-Avoidance

- 项目：[PX4/PX4-Avoidance](https://github.com/PX4/PX4-Avoidance)
- 技术：PX4、ROS、MAVROS、深度相机、点云、局部/全局规划
- 值得借鉴：相机与飞控数据流、伴随计算机边界、仿真先行原则。
- 不复用原因：已超出简单分类 Demo，依赖和计算量都过大。
- 结论：**当前排除**。

### 14. ThermalDrone

- 项目：[jacobfeldgoise/ThermalDrone](https://github.com/jacobfeldgoise/ThermalDrone)
- 技术：3DR Solo、DroneKit、Raspberry Pi Zero、Pi Camera、FLIR
- 许可证：未见明确许可证
- 值得借鉴：树莓派采集传感器后通过 MAVLink 向飞控发指令的总体分工。
- 不复用原因：硬件、系统、DroneKit 和 Python 版本都过旧，且无明确许可证。
- 结论：**只做历史参考**。

### 15. MAVSDK Drone Show

- 项目：[alireza787b/mavsdk_drone_show](https://github.com/alireza787b/mavsdk_drone_show)
- 技术：PX4、MAVSDK、SITL、多机、任务和地面站
- 许可证：非商业、小企业和商业多轨授权
- 值得借鉴：SITL 验证、运行状态和操作安全文档。
- 不复用原因：多机和地面站规模远超目标，许可证也不如 BSD/MIT/Apache 简单。
- 结论：**不进入第一版代码路径**。

### 16. Ultralytics

- 项目：[ultralytics/ultralytics](https://github.com/ultralytics/ultralytics)
- 技术：YOLO 检测/分类/跟踪，多种模型导出格式
- 许可证：AGPL-3.0 或商业授权
- 值得借鉴：ARM/树莓派模型导出和基准测试方法。
- 不复用原因：
  - 当前只需要单帧二分类；
  - YOLO 检测增加模型、后处理和许可证复杂度；
  - 树莓派 NCNN/ARM 组合曾出现版本兼容问题，必须单独锁定和实测。
- 结论：**若以后从分类升级为目标检测，再单独立项评估**。

## D. 第二轮补充：事件触发、状态机与模块边界

### 17. Intelligent-Quads/iq_gnc

- 项目：[Intelligent-Quads/iq_gnc](https://github.com/Intelligent-Quads/iq_gnc)
- 技术：ArduPilot、ROS、MAVROS、Python/C++
- 许可证：MIT
- 与本 Demo 最相关的内容：
  - `sr_sol.cpp` 示例会执行搜索航线，直到 YOLO 检测到人，再触发降落；
  - 提供高层航点、模式切换和状态读取函数；
  - 另有订阅者示例，展示外部感知结果如何进入飞行任务节点。
- 值得借鉴：
  - 检测器只发布“已检测”事实，任务层负责决定飞行动作；
  - 事件在状态机中只消费一次，防止同一检测结果重复触发；
  - 飞行动作完成后再进入下一次感知阶段。
- 不照搬：
  - ArduPilot/MAVROS 控制层；
  - 搜索救援航线、YOLO 实时检测和触发降落动作。
- 结论：**第二轮最贴近目标流程的参考项目**。把“检测到人后降落”替换成“分类完成后低速前飞”即可得到同一种任务结构。

### 18. Auterion/PX4 ROS 2 Interface Library

- 项目：[Auterion/px4-ros2-interface-lib](https://github.com/Auterion/px4-ros2-interface-lib)
- 技术：PX4、ROS 2、C++，部分 Python 绑定
- 许可证：BSD-3-Clause
- 与本 Demo 最相关的内容：
  - `Mode Executor` 是可启动飞行模式并等待完成的状态机；
  - 示例使用完成回调串联 `Takeoff -> Custom Mode -> RTL -> Wait Disarm`；
  - 模式失效、节点无响应、人工切换模式时由 PX4 处理控制权和失效保护。
- 值得借鉴：
  - 每个状态必须返回明确的成功/失败结果；
  - 上一状态失败时不得继续向前执行；
  - 人工遥控或地面站应随时可以夺回控制权；
  - 状态切换应由完成事件驱动，而不是散落的固定延时。
- 不照搬：
  - ROS 2、uXRCE-DDS、C++ 模式注册和 PX4 消息版本匹配；
  - 第一版不需要动态注册外部飞行模式。
- 结论：**状态机语义非常值得复用，运行时不引入**。

### 19. MikeS96/autonomous_landing_uav

- 项目：[MikeS96/autonomous_landing_uav](https://github.com/MikeS96/autonomous_landing_uav)
- 技术：PX4、Gazebo、ROS、MAVROS、OpenCV、Kalman Filter、PID
- 许可证：MIT
- 相关包：
  - `mavros_off_board`：仿真、模型和基础飞行脚本；
  - `object_detector`：目标检测与跟踪；
  - `drone_controller`：根据感知结果控制无人机。
- 值得借鉴：
  - 感知、飞控适配和任务控制分成独立边界；
  - 只有第一份有效估计产生后才启动控制器；
  - 仿真和真实机载电脑使用同一总体工作流。
- 不照搬：
  - 着陆板特征匹配、Kalman 跟踪和降落 PID；
  - ROS/MAVROS 工作区和旧版 Gazebo 配置。
- 结论：**适合参考包边界和“有效识别后才激活动作”的门控**。

### 20. dji-sdk/Tello-Python

- 项目：[dji-sdk/Tello-Python](https://github.com/dji-sdk/Tello-Python)
- 技术：Tello SDK、Python 2.7、H.264、姿态识别
- 许可证：MIT
- 与本 Demo 最相关的内容：
  - 官方 `Tello_Video_With_Pose_Recognition` 从视频中抽取单帧；
  - 把特定姿态识别结果直接绑定到飞行控制命令；
  - 命令脚本可按顺序执行离散飞行动作。
- 值得借鉴：
  - 最小演示不一定需要 ROS、SLAM 或持续跟踪；
  - 识别结果应先映射成有限的动作意图，再交给飞控；
  - 离散动作比连续视觉伺服更适合当前低速 Demo。
- 不照搬：
  - Tello 协议、Python 2.7、旧 H.264 解码和姿态识别实现。
- 结论：**是最小交互形式的好例子，但不能作为 PX4/树莓派代码基础**。

### 21. amov-lab/Prometheus

- 项目：[amov-lab/Prometheus](https://github.com/amov-lab/Prometheus)
- 技术：PX4、ROS、MAVROS、Gazebo、检测、规划、控制
- 许可证：GitHub 标识 Apache-2.0，但 README 同时写有“仅限个人、不可商用”的附加表述，复用前必须进一步澄清
- 值得借鉴：
  - 控制、目标检测、规划和仿真模块分区；
  - 提供多个可独立运行的功能 Demo；
  - 中文资料较多，便于理解 PX4 伴随计算机软件的完整边界。
- 不照搬：
  - 整套平台、编译脚本、规划和集群功能；
  - 在许可证表述澄清前不复制源码。
- 结论：**适合阅读总体模块图，不适合给简单 Demo 增加依赖**。

### 22. CERLAB UAV Autonomy Framework

- 项目：[Zhefan-Xu/CERLAB-UAV-Autonomy](https://github.com/Zhefan-Xu/CERLAB-UAV-Autonomy)
- 技术：C++、ROS、PX4、MAVROS、Gazebo、检测、规划、控制
- 许可证：MIT
- 值得借鉴：
  - `autonomous_flight`、`onboard_detector`、`tracking_controller` 和 `uav_simulator` 彼此独立；
  - 同一模块划分覆盖仿真和 PX4 实飞；
  - 顶层任务包只编排能力，不把检测细节写入飞控适配层。
- 不照搬：
  - 地图、轨迹优化、动态避障和多个 git submodule；
  - ROS Melodic/Noetic 环境。
- 结论：**模块化参考价值高，但远超第一版范围**。

### 23. Aerostack2

- 项目：[aerostack2/aerostack2](https://github.com/aerostack2/aerostack2)
- 技术：ROS 2 Humble、C++、Python、行为树、多平台适配
- 许可证：BSD-3-Clause
- 值得借鉴：
  - 飞行平台、行为、行为树、Python API、仿真资源彼此分离；
  - 强调平台无关和 Sim2Real；
  - 项目可只安装所需模块。
- 不照搬：
  - 多机框架、行为树运行时和完整 ROS 2 基础设施；
  - 当前六个左右状态用 Python `Enum` 和显式循环已经足够。
- 结论：**只参考“能力层与任务编排层分离”，不引入框架**。

### 24. GRVC UAV Abstraction Layer

- 项目：[grvcTeam/grvc-ual](https://github.com/grvcTeam/grvc-ual)
- 技术：ROS、C++/Python、PX4、ArduPilot、DJI、Crazyflie、Gazebo/AirSim
- 许可证：MIT
- 值得借鉴：
  - 统一 UAV 接口下面挂接 MAVROS、MAVLink、DJI、Crazyflie 和仿真后端；
  - 上层任务不感知具体飞控或仿真器；
  - 与本 Demo 的 `FlightController` 假后端、MAVSDK 后端思路一致。
- 不照搬：
  - 老版本 PX4/ROS 兼容层；
  - 多飞控后端和配置器。
- 结论：**强化了保留窄接口和假飞控测试后端的必要性**。

## 总排序

```text
立即阅读并准备复用：
MAVSDK-Python
PX4-gazebo-models
TensorFlow Lite Raspberry Pi classification
Picamera2

重点参考设计：
PixEagle
PX4 ROS 2 camera bridge tutorial
AIRo FSM
teNNo test modes
iq_gnc perception event
PX4 ROS 2 Mode Executor
autonomous_landing_uav package boundaries

暂不进入代码路径：
PX4-ROS2-Gazebo-YOLOv8
px4-offboard ROS 2
Clover
IMX500 model zoo
Tello-Python
Prometheus
CERLAB UAV Autonomy
Aerostack2
GRVC UAL
PX4-Avoidance
ThermalDrone
MAVSDK Drone Show
Ultralytics
```
