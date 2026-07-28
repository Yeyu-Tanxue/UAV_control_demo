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

暂不进入代码路径：
PX4-ROS2-Gazebo-YOLOv8
px4-offboard ROS 2
Clover
IMX500 model zoo
PX4-Avoidance
ThermalDrone
MAVSDK Drone Show
Ultralytics
```
