# L4R_NLB_fall → YOLO segmentation conversion report

- 类别：`ego_track_area`；
- 标签来源：JSON中 `relative position = ego` 的左右钢轨点；
- 官方mask包含所有轨道，未直接作为YOLO标签；
- 图片 / JSON / mask：1701 / 1699 / 1701；
- 可用 / 排除：1634 / 65；
- 排除原因：`{"ego_track_count_0": 50, "self_intersecting_polygon": 15}`；
- 无JSON图片：2；
- 轨道 / 道岔标注：2790 / 529。

## 连续帧块划分

| split | 图片数 | 时间块数 |
|---|---:|---:|
| train | 1210 | 27 |
| val | 213 | 1 |
| test | 211 | 1 |

相邻frame_id先归入同一时间块，再按完整块划分，避免相近画面跨split。
RailGoerl24仍是最终域内验证来源；本数据主要用于轨道分割预训练。
