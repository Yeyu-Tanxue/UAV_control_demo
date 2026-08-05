# L4R_NLB winter 转 YOLO 轨道分割数据

本数据用于预训练单类别轨道分割模型：

```text
class 0: ego_track_area
```

## 数据位置

解压后的实际数据根目录是外层目录中的同名子目录。以下使用占位符表示，不在仓库中记录本机绝对路径：

```text
<L4R_NLB_winter_root>
```

其中包含 `images/`、`annotations/`、`masks/` 和 `camera/`。

## 转换命令

在 `UAV_control_demo` 根目录运行：

```powershell
python tools\prepare_l4r_nlb_yolo.py `
  --source-root "<L4R_NLB_winter_root>" `
  --materialize-mode hardlink
```

输出目录：

```text
output/training-images/l4r_nlb_winter_yolo/
  dataset.yaml
  manifest.csv
  audit_report.json
  README.md
  images/{train,val,test}/
  labels/{train,val,test}/
```

图片使用NTFS硬链接，不重复占用约3.6 GiB空间。`images/` 和 `labels/` 是可重新生成的本地训练文件，不提交Git。

## 标签转换原则

官方mask会同时包含ego、left、right等所有已标轨道。在存在平行线路的画面中，直接使用mask会让模型同时学习多条轨道，因此本项目不直接使用官方mask作为标签。

转换器读取JSON，只选择：

```text
relative position = ego
```

然后用：

```text
left rail points + reverse(right rail points)
```

构成 `ego_track_area` 多边形，并转换为YOLO归一化分割坐标。

## 当前审计结果

- 图片：2,533张；
- JSON和mask：各2,441份；
- 可用于YOLO：2,380张；
- 无ego轨道：39张；
- 多边形自交：20张；
- 多边形面积过小：2张；
- 只有图片、没有JSON：92张。

最终划分为1,889张train、250张val、241张test。划分单位是连续250个frame id组成的时间块，不会把相近画面随机拆到不同split。

L4R_NLB用于预训练，最终模型选择和效果报告仍以人工确认的RailGoerl24 val/test为准。
