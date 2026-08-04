# UAV Control Demo

本仓库用于实现一个尽量简单、可解释、可逐步验证的无人机演示：

1. 起飞并悬停；
2. 获取一帧图像；
3. 用轻量 CNN 完成一次分类；
4. 低速向前飞行一小段；
5. 再次悬停并重复识别；
6. 完成若干轮后降落。

当前阶段只开展方案调研和最小架构设计，暂不实现完整飞行功能。

## 调研资料

相似项目的筛选结果放在 [`docs/research/similar-projects/`](docs/research/similar-projects/README.md)：

- `README.md`：调研结论、优先复用清单和建议架构；
- `PROJECT_NOTES.md`：逐个项目的复用点、限制和许可证说明；
- `reuse-matrix.csv`：可排序、可继续补充的项目复用矩阵。

0.92 m 与 2.5 m 铁轨视觉训练图像的来源、许可和高度核验记录放在
[`data/training-images/`](data/training-images/README.md)。其中 2.5 m 档已有距轨面
2.45 m 的真实公开数据候选；0.92 m 档暂未找到可核验高度的真实公开集，先采用可配置
Blender 铁路场景生成精确高度样本，后续再进行受控实拍。

X500 Demo 的采购清单和二手价格核验见
[`output/采购套件价格核验表.csv`](output/采购套件价格核验表.csv)。表格沿用原
`UAV_control` 项目的六列采购核验格式。更细的价格依据和逐项新旧区间保存在
[`docs/research/hardware/x500-demo-cost.csv`](docs/research/hardware/x500-demo-cost.csv)。
两张表均以 2026-07-29 可查的厂商价格为锚点，二手价格是采购预算估算，不是实时成交报价。

本仓库不直接收录第三方项目源码。后续确需复制或修改代码时，必须先核对项目许可证、具体文件版权声明和版本，再保留相应归属信息。
