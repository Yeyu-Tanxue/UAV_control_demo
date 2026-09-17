# 动态地面投影诊断

新增 ground_projection.py 将固定相机参数与动态 VehicleState 组合。输出地面坐标
以机体正下方为原点，X 水平朝机头方向、Y 向右，单位米。它是去掉横滚/俯仰的
水平航向坐标系；PX4 的 roll/pitch 采用 FRD 到 NED 约定。固定安装在 FLU 中
定义，因此计算时明确应用 diag(1,-1,-1)。相机偏移也随姿态旋转。

VehicleStateBuffer 只插值被两侧样本包围的时间点，拒绝时钟不同、过大的遥测
间隙和外推。低倾角 Demo 使用最短角插值；超出 35 度倾角的投影被拒绝。
后续大姿态运动应改成四元数 SLERP。

pixels_to_ground 支持 OpenCV 去畸变，返回地面坐标与有效标志。朝天/地平线
射线返回无效值。ground_to_image_homography 对应去畸变图像。birdseye 默认
前方 8 米、左右各 2 米、每像素 0.02 米，并检查图像与标定分辨率一致。

## 只读在线入口

WSL 仓库根目录，在已有 Gazebo/PX4 运行且 MAVSDK 端口可用时：

```bash
PYTHONPATH=src .venv/bin/python -m uav_demo.projection_diagnostic \
  --home-above-ground <实测Home高程减轨道平面高程，单位米> \
  --output captures/projection/check_001 --count 20
```

输出目录必须尚不存在。脚本只订阅遥测和读取相机 PNG，不解锁、不起飞、不发送
控制指令。生成逐帧 BEV PNG 和 projection.jsonl（姿态、高度来源、时间质量、
单应矩阵或拒绝原因）。端口不要与已有 MAVSDK 服务争用。

当前接入采用遥测接收时刻与 PNG 文件落盘时刻的近似匹配，明确标记为
host_monotonic_approximate；没有把它称为曝光级同步。真实图像时间戳、PX4 时间
与主机时间的转换仍需后续接入。老截图不能匹配本次实时遥测。

高度来自 relative_altitude_m + 显式 Home 到目标平面的高差。不能直接把相对
Home 高度当 AGL；仿真起飞台、机体原点、轨道顶面也不必在同一高度。尚未安装
下视测距仪，本模块没有宣称获得真实测距 AGL。

现有 YOLO 控制入口尚未切换到本模块。先通过在线诊断图确认坐标与尺度，再接
米制轨道拟合和控制。合成测试验证的是数学与坐标关系，不代表真实试飞已完成。
