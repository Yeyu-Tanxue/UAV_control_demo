# 无积雪直线轨道世界

第一版 `rail_demo` 是为 PX4 X500 低速视觉 Demo 准备的轻量 Gazebo Harmonic
世界，不依赖第三方 mesh，也不包含积雪。

## 几何参数

| 项目 | 当前值 |
|---|---:|
| 轨道长度 | 30 m |
| 标准轨距（两钢轨内侧面） | 1.435 m |
| 轨枕间距 | 0.6 m |
| 轨枕数量 | 51 |
| 轨枕长度 | 2.6 m |
| 道床宽度 | 3.6 m |
| 道床长度 | 32 m |

轨道沿 Gazebo 世界的 X 轴布置，中心线为 `Y=0`。X500 默认生成在
`(-13, -3, 0.2)` 的起降坪上，避免出生时与钢轨或轨枕发生碰撞。

## 文件位置

```text
simulation/gazebo/
├── models/rail_track/
│   ├── model.config
│   └── model.sdf
└── worlds/rail_demo.sdf
```

`model.sdf` 和 `rail_demo.sdf` 由以下脚本生成：

```bash
python3 tools/generate_gazebo_rail_world.py
```

修改长度、轨距或轨枕间距时，应修改生成器顶部的常量后重新生成，不要手工修改
生成的 `model.sdf`。

## 启动

确认没有其他 PX4/Gazebo 实例运行，然后在 WSL Ubuntu 22.04 中执行：

```bash
cd "/mnt/e/冰雪天气轨道图像采集/UAV_control_demo"
chmod +x scripts/*.sh
./scripts/start_rail_sitl.sh
```

该脚本会先加载仓库内的 `rail_demo.sdf`，再以 standalone 模式启动 PX4 并生成
X500；无需把自定义世界复制到 `PX4-Autopilot`。只做无界面测试时可执行：

```bash
HEADLESS=1 ./scripts/start_rail_sitl.sh
```

结束仿真时在启动它的终端按 `Ctrl+C`，脚本会一并关闭自己启动的 Gazebo
服务端和界面。

QGroundControl 与原来的仿真一样自动连接。此时 Python 飞行 Demo 仍使用：

```bash
./scripts/run_sitl_demo.sh
```

当前 Python Demo 会从侧面起降坪沿机头方向飞行，并不会自动移动到轨道正上方。
这是下一阶段加入下视相机与轨道对准动作时需要完成的内容。

## 重点观察

- 两根钢轨是否连续、平行；
- 轨枕是否均匀分布且没有闪烁或悬空；
- 轨距相对于 X500 是否合理；
- X500 是否在侧面起降坪生成，而不是落在钢轨上；
- Gazebo `real_time_factor` 是否接近 1；
- QGC 是否仍能收到姿态、位置和飞行模式数据。
