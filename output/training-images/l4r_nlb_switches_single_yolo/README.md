# L4R_NLB multi-season railway-switch dataset

YOLO类别模式：`single`；类别：`switch`。无道岔但有完整 JSON 的图片保留为空标签负样本。
相邻帧按“季节 + frame_id 时间块”整体划分，避免连续画面跨 split。

- 可用图片：7056（正样本 772，负样本 6284）
- 道岔框：1130，类别分布：`{"switch": 1130}`
- 框尺寸：`{"width_p10": 26.0, "width_median": 67.0, "height_p10": 12.0, "height_median": 39.0}`

| split | 图片 | 正样本 | 时间块 |
|---|---:|---:|---:|
| train | 5643 | 580 | 60 |
| val | 719 | 107 | 7 |
| test | 694 | 85 | 7 |
