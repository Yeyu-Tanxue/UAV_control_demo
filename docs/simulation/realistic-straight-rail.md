# 带贴图的直轨 Demo

当前活动世界 `rail_demo_realistic` 只使用 Part 1 直轨。8 个 4 m 模块沿世界
X 轴首尾拼接，总长度约 32 m。Part 2 弯轨和 Part 3 岔道不参与本轮仿真，避免
给现阶段视觉识别增加不必要的目标变化。

## 启动

在 WSL Ubuntu 22.04 中执行：

```bash
cd "/mnt/e/冰雪天气轨道图像采集/UAV_control_demo"
chmod +x scripts/start_realistic_rail_sitl.sh
./scripts/start_realistic_rail_sitl.sh
```

无界面验证：

```bash
HEADLESS=1 ./scripts/start_realistic_rail_sitl.sh
```

默认使用带单目相机的 X500。无人机位于轨道入口前的起飞坪，机头沿世界
`+X`（直轨延伸方向），相机固定向前下方俯视 35 度，水平视场 110 度。
保持 PX4 与 Gazebo 运行后，第二个终端启动本地视觉闭环：

```bash
./scripts/run_sitl_demo.sh
```

活动任务不再执行起飞后的固定前移，也不再把“保存到图片”当成识别成功。
每一步都在任务进程本地读取 Gazebo 相机帧，运行 Spring YOLO 分割，从掩膜
计算中心偏差与航向误差，再发出短时前向、横向和偏航速度。识别失败时保持
零速度，连续失败达到门限后降落。

默认执行 8 个视觉控制脉冲；首轮建议使用：

```bash
./scripts/run_sitl_demo.sh --control-steps 3
```

详细几何和树莓派本地部署见
[`docs/vision/onboard-visual-control.md`](../vision/onboard-visual-control.md)。

## 当前取舍

- GLB 只作为视觉网格，地面平面负责碰撞；
- 保留模型内嵌 UV 与 4K PBR 贴图；
- 不添加弯轨、岔道、积雪和复杂环境；
- 原有程序化 `rail_demo` 保留作为低性能开销的回退世界。
