# RailGoerl24 首批200张标注集

- train：136张，允许模型预标注后人工修正；
- val：32张，完全人工确认，不参与训练；
- test：32张，完全人工确认，不参与训练或伪标签迭代；
- 覆盖视频序列：train 53 / val 4 / test 4；
- 图片副本大小：69.4 MiB。

图片位于 `images/train`、`images/val`、`images/test`。文件名前的三位数字对应 `annotation_batch.csv` 中的 `batch_order`。
标注 `ego_track_area` 多边形：只覆盖当前行驶股道两条内侧轨缘之间的区域。道岔走向不明确时不要猜测，改为 excluded 并填写原因。
