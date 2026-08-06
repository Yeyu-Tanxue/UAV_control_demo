# L4R_NLB_spring → YOLO segmentation conversion report

- 类别：`ego_track_area`；
- 标签来源：JSON中 `relative position = ego` 的左右钢轨点；
- 官方mask包含所有轨道，未直接作为YOLO标签；
- 图片 / JSON / mask：2916 / 2916 / 2916；
- 可用 / 排除：2792 / 124；
- 排除原因：`{"ego_track_count_0": 101, "self_intersecting_polygon": 20, "tiny_polygon": 3}`；
- 无JSON图片：0；
- 轨道 / 道岔标注：3405 / 260。

## 连续帧块划分

| split | 图片数 | 时间块数 |
|---|---:|---:|
| train | 2255 | 11 |
| val | 254 | 3 |
| test | 283 | 2 |

相邻frame_id先归入同一时间块，再按完整块划分，避免相近画面跨split。
RailGoerl24仍是最终域内验证来源；本数据主要用于轨道分割预训练。
