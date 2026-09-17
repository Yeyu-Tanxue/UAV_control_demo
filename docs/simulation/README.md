# 前两步仿真操作手册

> 当前基于 YOLO 分割的视觉闭环架构、中心线算法和 PX4 控制流程见
> [`visual-closed-loop-technical-overview.md`](visual-closed-loop-technical-overview.md)。
> 最新的相机标定、动态轨面投影与米制闭环结果见
> [`metric-closed-loop.md`](metric-closed-loop.md)。
> 本文件以下内容保留为早期基线仿真操作记录。

本手册只覆盖当前最小目标：

1. PX4 SITL + Gazebo X500 + QGroundControl 基线；
2. Python 执行“悬停—模拟识别—低速前飞—悬停”的两轮任务。

铁轨世界、Gazebo 相机和 CNN 暂不进入本轮。

## 已锁定环境

- Ubuntu 22.04（WSL2）；
- PX4 Autopilot `v1.17.0`；
- Gazebo Harmonic；
- QGroundControl 5.x；
- Python 3.10；
- MAVSDK-Python `3.15.3`。

不要混用 Gazebo Classic、ROS 1 或旧版 `gazebo-classic_iris` 教程。

## 1. 启动 PX4 SITL 与 Gazebo

在第一个 Ubuntu/WSL 终端中：

```bash
cd "/mnt/e/冰雪天气轨道图像采集/UAV_control_demo"
chmod +x scripts/*.sh
./scripts/start_px4_sitl.sh
```

脚本等价于在 `~/PX4-Autopilot` 中运行：

```bash
make px4_sitl gz_x500
```

首次运行会编译 PX4，耗时明显长于后续运行。成功标志：

- Gazebo 中出现 X500 四旋翼；
- PX4 终端出现 `pxh>`；
- 没有持续刷新的致命错误。

## 2. 打开 QGroundControl 验证基线

Windows 安装位置：

```text
E:\QGroundControl\bin\QGroundControl.exe
```

QGC 默认监听 UDP 14550，正常情况下会自动发现 PX4。先只观察：

- 载具类型为四旋翼；
- 飞行模式、姿态和高度数据持续更新；
- Vehicle ready 状态没有关键故障。

QGC 和 Python 不要同时发送起飞或模式切换命令。运行 Python Demo 时，QGC
只用于监控和人工接管。

## 3. 建立 Python 环境

在第二个 WSL 终端中：

```bash
cd "/mnt/e/冰雪天气轨道图像采集/UAV_control_demo"
chmod +x scripts/*.sh
./scripts/setup_python.sh
```

先运行不会连接无人机的检查：

```bash
./scripts/run_dry_demo.sh
```

预期状态顺序为：

```text
CONNECTING -> TAKING_OFF
-> HOVERING -> RECOGNIZING -> MOVING_FORWARD -> SETTLING
-> HOVERING -> RECOGNIZING -> MOVING_FORWARD -> SETTLING
-> LANDING -> COMPLETE
```

## 4. 运行真实 SITL 动作

保持 PX4/Gazebo 正在运行，然后在第二个 WSL 终端执行：

```bash
./scripts/run_sitl_demo.sh
```

默认参数：

- 起飞高度：2.0 m；
- 模拟识别时间：3 s；
- 前飞速度：0.2 m/s；
- 每次前飞距离：2.0 m；
- 停稳时间：2 s；
- 循环次数：2。

可在 SITL 中保守调整，例如：

```bash
./scripts/run_sitl_demo.sh \
  --cycles 1 \
  --forward-speed 0.1 \
  --forward-distance 0.2
```

代码限制高度不超过 5 m、速度不超过 1 m/s、单次距离不超过 5 m。MAVSDK
后端必须显式携带 `--confirm-sitl`；现阶段禁止把该命令直接用于真机。

## 5. 停止与异常处理

- 正常任务完成后自动退出 Offboard 并降落；
- 识别拒绝或程序异常时，请求零速度、退出 Offboard 并降落；
- 首次 `Ctrl+C` 会优先等待安全降落清理完成；连续中断也不会取消正在执行的降落；
- 若程序未能确认降落，PX4 会保持 Land 指令。立即在 QGC 中人工接管，确认接地前绝不能 Disarm。

PX4/Gazebo 终端最后使用 `Ctrl+C` 关闭。

## 常见问题

### Python 一直等待连接

确认 PX4 终端仍在运行，并且 UDP 14540 没被另一个 MAVSDK 程序占用：

```bash
ss -lunp | grep 14540
```

### QGC 看不到载具

先重启 QGC，再重启 SITL。若 WSL 使用 NAT 网络且 Windows 收不到 UDP 14550，
需要单独配置 WSL mirrored networking 或把 MAVLink 目标地址设为 Windows 主机地址。

### Gazebo 窗口不出现

先确认 WSLg 可用：

```bash
echo "$DISPLAY"
echo "$WAYLAND_DISPLAY"
```

显卡渲染异常时，可临时尝试：

```bash
PX4_GZ_SIM_RENDER_ENGINE=ogre ./scripts/start_px4_sitl.sh
```
