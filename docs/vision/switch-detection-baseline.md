# 道岔检测基线

当前 Demo 推荐把所有道岔统一检测为一个 `switch` 类。L4R_NLB 的
`fork/merge` 是按轨道拓扑方向定义的；相机从相反方向观察同一组钢轨时，视觉上的
“分出”和“汇入”可能互换，因此不适合作为跨数据集飞控类别。

道岔检测只负责报告“前方出现拓扑事件”。飞行方向仍由 `ego_track_area` 分割结果
计算：提取候选轨道中心线、计算角度，再按预设任务选择支路。

## 1. 数据转换

春、秋、冬三季数据统一转换为单类 YOLO 检测数据：

```powershell
python tools/prepare_l4r_switch_yolo.py `
  --source "winter=E:\冰雪天气轨道图像采集\图像数据\L4R_NLB_winter" `
  --source "fall=E:\冰雪天气轨道图像采集\图像数据\L4R_NLB_fall\L4R_NLB_fall" `
  --source "spring=E:\冰雪天气轨道图像采集\图像数据\L4R_NLB_spring" `
  --class-mode single `
  --output-dir output/training-images/l4r_nlb_switches_single_yolo
```

转换结果：

- 7,056 张可用图像，772 张道岔正样本，6,284 张负样本；
- 1,130 个有效 `switch` 框；
- train/val/test 分别为 5,643/719/694 张；
- 按“季节 + 250 帧时间块”划分，避免相邻视频帧跨集合泄漏；
- 只使用同时存在图片和完整 JSON 的帧，源数据不会被修改。

审计报告位于
`output/training-images/l4r_nlb_switches_single_yolo/audit_report.json`。

## 2. 训练和独立测试

道岔框多数较小，使用 960 输入分辨率。当前单类模型从两类基线权重继续微调 5
轮：

```powershell
python tools/switch_detection.py train `
  --model output/training-runs/switch-detection/l4r_multiseason_kind_yolo26n_5e/weights/best.pt `
  --data output/training-images/l4r_nlb_switches_single_yolo/dataset.yaml `
  --epochs 5 --imgsz 960 --batch 8 --workers 2 `
  --name l4r_multiseason_single_yolo26n_5e --exist-ok

python tools/switch_detection.py validate `
  --model output/training-runs/switch-detection/l4r_multiseason_single_yolo26n_5e/weights/best.pt `
  --data output/training-images/l4r_nlb_switches_single_yolo/dataset.yaml `
  --split test --imgsz 960 --batch 8 --workers 2 `
  --name l4r_multiseason_single_yolo26n_5e_test
```

| 模型 | 集合 | P | R | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 六类 `fork/merge + left/right/unknown` | val | 0.360 | 0.251 | 0.123 | 0.052 |
| 两类 `fork/merge` | val | 0.467 | 0.238 | 0.230 | 0.087 |
| 两类 `fork/merge` | test | 0.269 | 0.284 | 0.186 | 0.078 |
| 单类 `switch` | val | 0.491 | 0.333 | 0.351 | 0.143 |
| 单类 `switch` | test | 0.433 | 0.336 | 0.349 | 0.137 |

最佳权重位于
`output/training-runs/switch-detection/l4r_multiseason_single_yolo26n_5e/weights/best.pt`。

## 3. RailGoerl24 首批 200 张跨域检查

```powershell
python tools/switch_detection.py preannotate `
  --model output/training-runs/switch-detection/l4r_multiseason_single_yolo26n_5e/weights/best.pt `
  --source output/training-images/railgoerl24/batch_001_200/images `
  --output output/preannotations/railgoerl24_switches_single_l4r_v0 `
  --imgsz 960 --conf 0.15 --max-det 10 --nms-iou 0.50
```

0.15 阈值下，200 张中有 95 张出现检测，共保留 118 个框；按每张图最高置信度
统计，阈值为 0.20/0.30/0.50 时分别有 57/44/12 张触发。3 张
`switch_review` 帧中，第 131、133 张命中，第 132 张漏检。

普通人员和轨旁物体序列中仍有高置信误报，说明 L4R_NLB 到 RailGoerl24 存在明显
域差异。当前模型适合生成草稿和筛选人工标注图，不可直接驱动飞行器。下一轮应优先
精标 RailGoerl24 中的真道岔、误报和漏报帧，再进行微调。

检查清单位于
`output/preannotations/railgoerl24_switches_single_l4r_v0/review_manifest.csv`。

## 4. 首批 Labelme 人工复核

首批工作区包含 80 张图片：完整 `Weichenstellung` 序列均匀抽取 30 张、不同序列的
高置信疑似误报 30 张，以及模型未检出的普通轨道 20 张。生成或恢复工作区：

```powershell
python tools/prepare_labelme_switch_review.py prepare
```

工作区位于
`output/manual-annotations/railgoerl24_switch_labelme_batch_001/images`。在 Labelme 中：

1. 正确的模型框直接保留，位置不准则调整矩形；
2. 普通轨道误报应删除所有框；
3. 漏检时为每个可见道岔绘制 `switch` 矩形；
4. 检查整张图后勾选 `reviewed`，过远或无法判断时同时勾选 `uncertain`；
5. 按 Ctrl+S 保存，不重命名图片或 JSON。

检查进度及格式：

```powershell
python tools/prepare_labelme_switch_review.py status
```

脚本默认保留已经存在的 JSON；只有明确需要重新生成全部草稿时才使用
`prepare --overwrite`。

## 5. Demo 控制状态建议

1. `TRACK_FOLLOW`：由轨道区域中心线计算横向偏差和飞行角度，低速前进；
2. 连续至少 3 帧检测到 `switch`，并且轨道分割也出现两个稳定候选中心线时，进入
   `HOVER_RECOGNIZE`；
3. 悬停后累计多帧结果，按任务预设选择左/右支路，不从 `fork/merge` 类名推断方向；
4. 锁定所选分割区域的中心线，恢复低速 `TRACK_FOLLOW`；
5. 人员检测优先级最高，命中后立即悬停，不受道岔状态覆盖；
6. 任何视觉结果置信不足、跨帧不一致或中心线丢失时，保持悬停。

单帧建议先用 0.30 作为人工评估起点，但最终阈值必须在 RailGoerl24 人工确认集上
按误报率选择，不能仅根据 L4R_NLB 的 test 指标决定。
