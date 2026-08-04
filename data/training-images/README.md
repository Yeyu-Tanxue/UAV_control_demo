# 铁轨视觉训练图像来源（0.92 m / 2.5 m）

调研日期：2026-08-04

这里保存数据来源、许可和下载说明，不把数 GB 的第三方训练图片直接提交到 Git。
本地下载后的数据分别放入 `raw/`、`generated/` 和 `processed/`；这些目录已被
`.gitignore` 排除。

## 结论先行

- **2.5 m 档有高质量真实候选。** RailGoerl24 的相机距轨面 **2.45 m**，与目标只差
  5 cm。数据包含 12,205 张 1920×1080 RGB 帧，视角为机车前向、略向下俯视；欧盟
  开放数据记录为 **CC0 1.0**。如果项目允许高度误差 `±0.10 m`，它可作为 2.5 m 档的
  主要真实数据，但原始元数据仍应保留为 `2.45`，不要篡改成 `2.50`。
- **没有找到可核验为 0.92 m 的真实公开铁轨图像集。** 搜索结果中的普通网页图片、
  人工拍摄图和车载数据通常没有相机离轨面高度，不能可靠地标成 0.92 m。
- **精确的 0.92 m 与 2.50 m 图像可先用 RailEnV-PASMVS 场景生成。** 该项目公开了
  238 MB 的 Blender 铁路场景，许可为 **CC BY 4.0**。原数据的三组相机高度是
  0.10/0.25/0.40 m，因此原始渲染不能直接当作 0.92 m 数据；需要在 `.blend` 中把
  相机设为 0.92 m 和 2.50 m 后重新渲染。
- 最终训练集建议采用“**真实 2.45 m + 精确高度合成图 + 本项目受控补拍**”。仅用合成图
  会有 sim-to-real 差距，0.92 m 档尤其需要后续自行补拍真实图片。

## 1. 2.5 m 档：RailGoerl24（首选真实数据）

论文明确写明：Axis P3925-R 相机装在 V22 机车前/后端，距轨面 **2.45 m**；镜头
3.6 mm，水平/垂直视场角为 85.7°/46.0°，相机略向下倾斜，图像底边对应车辆前方约
3 m。共有 61 段视频抽取的 12,205 帧，并带 33,556 个人员框标注。

- 数据主页：[RailGoerl24（欧盟开放数据目录）](https://data.europa.eu/data/datasets/0243de33-df91-47f0-a092-f3006e400c90)
- 高度依据：[RailGoerl24 论文 PDF，第 2 页 Fig. 3](https://arxiv.org/pdf/2504.00204)
- RGB 数据直链：[Annotated_RGB_data.7z](https://download.data.fid-move.de/dzsf/railgoerl24/Annotated_RGB_data.7z)
- 许可：数据目录分发元数据标注 [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/deed.en)

下载站目前有浏览器验证页，命令行可能只拿到 HTML 而不是 `.7z`。应使用浏览器完成验证
后下载，并在解压前确认文件类型。不要把压缩包提交到 Git。

适用范围：前向视角下的轨道存在性、轨道/非轨道场景分类、人员或障碍物识别预训练。
局限：它是机车视角而不是无人机正下视角；数据来自同一测试场，且人员场景主要用于评估
危险检测。若 Demo 的相机朝向明显不同，仍需本机位补拍。

## 2. 0.92 m 与 2.50 m 精确档：RailEnV-PASMVS 场景重渲染

RailEnV-PASMVS 是 Blender 中的合成铁路环境，可生成 RGB、深度图和轨道部件分割掩码。
公开记录包含 40 个场景、79,800 个原始渲染，以及带相机内外参的标注；数据许可为
CC BY 4.0。

- 数据主页：[Mendeley Data（CC BY 4.0）](https://data.mendeley.com/datasets/xrwb9m37gd/3)
- Zenodo 记录：[RailEnV-PASMVS](https://zenodo.org/records/5233840)
- Blender 场景：[`RailEnV-PASMVS.blend`](https://zenodo.org/api/records/5233840/files/RailEnV-PASMVS.blend/content)，237,961,288 bytes
- 真实照片补充包：[`PhysicalDataset.7z`](https://zenodo.org/api/records/5233840/files/PhysicalDataset.7z/content)，1,963,699,562 bytes
- 高度依据：[数据论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC8479407/)说明原始三相机位于轨面上方 0.10/0.25/0.40 m。

使用规则：

1. 只下载 `.blend` 即可开始制作精确高度合成集，不必先下载数 TB 的全部原始渲染。
2. 以轨顶面作为高度零点，分别设置相机光心 `z=0.92 m`、`z=2.50 m`。
3. 相机俯仰角、横向偏移、焦距、天气和光照应覆盖真实无人机的合理扰动范围，而不是每张
   图完全相同。
4. 输出目录必须分别命名为 `synthetic_h0p92m` 和 `synthetic_h2p50m`，并为每张图保存
   实际高度、俯仰、横滚、偏航、焦距和场景编号。
5. `PhysicalDataset.7z` 中有 320 张真实高分辨率照片，但来源视角多样且未给出这两个精确
   高度；它们只能标记为 `height_unknown`，用于域适配或人工复核，不能混入高度真值集。

## 3. 不应误用的候选

- [UAV-RSOD](https://www.nature.com/articles/s41597-024-03952-3) 是很好的低空铁路分割与
  障碍物数据，但论文明确飞行高度为 **10.5 m**，不适合作为 0.92/2.5 m 高度标签。
- [SynDRA-BBox](https://syndra.retis.santannapisa.it/syndrabox.html) 的合成相机距轨面
  **3.5 m**，可以做铁路场景预训练，但不能当成 2.5 m 真值。
- RailSem19、OSDaR23 等前向铁路数据虽然内容丰富，但公开资料没有给出与本任务一致的
  0.92/2.5 m 相机高度；只能放入 `height_unknown`，不能用透视变换后伪造高度标签。

## 4. 推荐目录与标签

```text
data/training-images/
  source-manifest.csv
  raw/
    railgoerl24_h2p45m/
    railenv_physical_height_unknown/
  generated/
    synthetic_h0p92m/
    synthetic_h2p50m/
  processed/
    train/
    val/
    test/
```

每张图片至少保留以下字段：

```text
file, source, real_or_synthetic, camera_height_m, height_verified,
pitch_deg, roll_deg, yaw_deg, focal_length_mm, scene_id, sequence_id,
license, split
```

数据划分必须按 `sequence_id` 或实际线路区段进行，不能把同一视频相邻帧随机拆到训练集和
验证集，否则会产生严重的数据泄漏。建议先完成：

- `2.5 m`：RailGoerl24 真实数据 + 少量 `synthetic_h2p50m`；
- `0.92 m`：`synthetic_h0p92m` 起步，再用相同相机和镜头在封闭/获准轨道环境中补拍；
- 两档分别留出独立线路或独立场景作为测试集，不只比较训练准确率。

## 5. 安全与版权

- 不要进入运营铁路或在线路上摆放物体采集数据；真实补拍应在封闭试验线、废弃轨道或取得
  管理方明确许可的环境中完成。
- RailGoerl24 虽为 CC0，仍建议在数据卡中记录来源；RailEnV-PASMVS 为 CC BY 4.0，发布
  衍生训练集或结果时必须保留署名和来源链接。
- 普通搜索引擎图片除非逐张具有明确许可，否则只作视觉参考，不下载进训练集。
