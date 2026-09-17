# Gazebo 相机固定几何

> 2026-09-11 在线核验修正：下文早期记录中的 `(0.12, 0, 0.18)` 是相机相对
> X500 模型原点的位置，不是相对 base_link。PX4 x500_base 合并时 base_link
> 位于模型 Z=0.24 m；相机相对 base_link 实际为 `(0.12, 0, -0.06)` m。
> loader 已据此修正，body_origin_in_model_m 可覆盖该模型专用默认值。
> 当前只支持父框架与模型坐标轴平行的这个 X500 配置；更换模型须重新解析位姿。

本文只固化视觉地面投影的前两部分：相机内参和相机相对机体的安装外参。飞行器
实时姿态、离地高度和动态单应矩阵不属于本阶段。

## 数据来源

代码不维护第二份手工参数，而是直接读取：

- `simulation/gazebo/models/mono_cam/model.sdf`：分辨率、水平视场角、帧率和裁剪距离；
- `simulation/gazebo/models/x500_mono_cam/model.sdf`：相机相对 `base_link` 的固定位姿。

读取入口为 `uav_demo.camera_geometry.load_gazebo_camera_geometry()`。加载时会检查相机
模型的 `<include><pose>` 与固定关节的 `<pose>` 是否一致，防止以后只改了其中一处。

## 相机内参

当前 Gazebo 相机为 640×480，水平视场角 110°。Gazebo 仿真使用理想针孔和方形
像素，因此：

```text
fx = fy = width / [2 tan(horizontal_fov / 2)]
        = 224.066412 px
cx = 320 px
cy = 240 px
```

内参矩阵为：

```text
K = [224.066412,   0,          320]
    [  0,          224.066412, 240]
    [  0,            0,          1]
```

由相同像素焦距和 480 像素高度得到垂直视场角约 93.9329°。SDF 没有设置镜头畸变，
本阶段采用 OpenCV 顺序 `(k1, k2, p1, p2, k3) = (0, 0, 0, 0, 0)`。

## 固定安装外参

相机中心在 Gazebo `base_link` 中的位置为：

```text
x = +0.12 m  （机体前方）
y =  0.00 m
z = +0.18 m  （机体上方）
```

安装姿态为 roll=0°、pitch=+35°、yaw=0°。按 SDF 的旋转约定，这使相机中心视线
在机体系中指向：

```text
[cos(35°), 0, -sin(35°)] = [0.819152, 0, -0.573576]
```

也就是“向前并向下”，不是向上仰视。

## 坐标轴转换

Gazebo 相机 link 使用：

```text
+X 前，+Y 左，+Z 上
```

OpenCV 光学坐标使用：

```text
+X 图像右，+Y 图像下，+Z 镜头前方
```

二者之间固定满足：

```text
x_optical = -y_link
y_optical = -z_link
z_optical =  x_link
```

`CameraMount.body_from_optical_rotation` 已显式包含这个轴转换。后续动态投影模块只需
再组合 PX4/Gazebo 的实时机体姿态与离地高度，不应重新猜测图像轴的正负方向。

## 下一阶段接口

下一阶段增加 `VehicleState` 和 `DynamicGroundProjector`：

```text
固定 CameraIntrinsics
固定 CameraMount
动态机体姿态 + 动态离地高度
                 ↓
当前帧的地面单应矩阵
```

相机帧和飞行状态必须按时间戳配对。动态投影验证通过以前，现有像素误差控制映射
继续保留，但不把它误认为米制控制结果。
