# RailGoerl24（2.45 m）数据准备与铁轨标注

本阶段的目标不是直接训练，而是先得到可复现、无相邻帧泄漏的数据清单，并从每段视频中均匀抽取少量画面做铁轨几何标注。原始图片和 XML 始终保留在仓库外。

## 一键生成清单

在仓库根目录运行：

```powershell
$python = "C:\Users\顾朱政霖\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python tools\prepare_railgoerl24.py `
  --dataset-root "E:\冰雪天气轨道图像采集\图像数据\Annotated_RGB_data" `
  --candidate-frames-per-sequence 8 `
  --seed 20260804 `
  --strict
```

默认输出到 `output/training-images/railgoerl24/`：

- `dataset_manifest.csv`：12,205 帧完整清单，包含人员/自行车框数、相机高度和 split；
- `rail_annotation_candidates.csv`：每个视频最多 8 帧，共约 500 帧；
- `audit_report.json`：供程序读取的审计统计；
- `audit_report.md`：供人工检查的摘要。

所有路径相对于 `Annotated_RGB_data`，因此清单不绑定某台电脑。工具只使用人工 XML，明确排除 `_auto_annots`。

## 为什么必须按视频划分

同一视频的相邻帧几乎相同。如果逐帧随机划分，训练集中的前后帧会出现在验证集或测试集，指标会虚高。工具把完整 `sequence_id` 分配到同一个 split，目标帧比例为 70% / 15% / 15%。

铁轨候选也按每段视频均匀抽样，不连续抽取相邻画面。`scenario_hint=object_on_track` 用于保留障碍场景；`scenario_hint=switch_review` 表示道岔候选，需要人工复核。

## 第一版铁轨标注规范

推荐使用 CVAT 的 **Polyline**，只建两个标签：

- `left_rail`：当前行驶股道左侧钢轨的内侧轨缘；
- `right_rail`：当前行驶股道右侧钢轨的内侧轨缘。

这里的“左/右”永远以画面底部、相机前进方向为准，不以地图方向为准。两条内侧轨缘的中点就是轨道中心，避免再人工画一条容易不一致的中心线。

标注规则：

1. 每条折线从画面底部向远方绘制，顺序保持一致；
2. 直线段至少 6 个点，曲线段在曲率变化处加点，通常 8–15 个点即可；
3. 点落在钢轨朝轨道中心一侧的清晰边缘，不要一会儿标内缘、一会儿标钢轨中心；
4. 遇到人员或小物体遮挡时，可沿短遮挡区连续标注；长距离不可见时不猜测；
5. 当前轨道无法确定、长距离重度遮挡或轨缘不可辨时，把 `rail_annotation_status` 改为 `excluded` 并填写 `exclude_reason`；
6. 第一版不训练道岔决策。道岔、多股轨道交叉和走向歧义画面统一排除，后续单独建立道岔子集。

抽查显示，数据里除了 `Weichenstellung.mp4`，其他序列也可能出现多股轨道。因此 `scenario_hint=normal` 不能代替人工判断；导入标注工具后仍需逐张确认“当前行驶股道”。

## 标注完成后的验收

在开始训练前检查：

- 每张有效图片恰好有一条 `left_rail` 和一条 `right_rail`；
- 两条线在同一图像纵坐标范围内有足够重叠；
- 左右线在画面底部没有交换；
- 中心线位于两轨之间，且随远方透视合理收敛；
- 同一视频中的标签定义一致；
- train / val / test 仍按原 `sequence_id`，不可在标注工具里重新随机拆分。

完成上述验收后，再把折线栅格化为两类轨线掩码，训练轻量分割网络。推理阶段先从两条轨线求中心线，再通过相机标定和地面单应性把像素中心转换到机体坐标；飞行偏角由前视点计算：

```text
flight_angle = atan2(lateral_offset_m, lookahead_distance_m)
```

人员检测命中、轨线置信度不足或偏角过大时保持悬停；只有人员区域安全且轨线稳定时，才低速向前飞一个短距离。
