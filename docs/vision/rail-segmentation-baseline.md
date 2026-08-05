# Rail-area segmentation baseline

This baseline converts the L4R_NLB winter ego rails into one YOLO segmentation
class, `ego_track_area`, and uses it to create reviewable draft labels for the
first 200 RailGoerl24 images.

## Environment used

- Windows, Python 3.12
- NVIDIA RTX 3060 Laptop GPU (6 GB)
- PyTorch 2.5.1 + CUDA 12.1
- Ultralytics 8.4.67
- `yolo26n-seg.pt`, image size 640, batch size 4

Example installation:

```powershell
python -m venv .venv-vision
.\.venv-vision\Scripts\python.exe -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
.\.venv-vision\Scripts\python.exe -m pip install ultralytics==8.4.67
```

## Reproduce the baseline

The dataset is generated first with `tools/prepare_l4r_nlb_yolo.py`. Then run:

```powershell
.\.venv-vision\Scripts\python.exe tools\rail_segmentation.py train --epochs 1 --name l4r_winter_yolo26n_sanity --exist-ok
```

Evaluate the best checkpoint on the temporally held-out test block:

```powershell
.\.venv-vision\Scripts\python.exe tools\rail_segmentation.py validate --model output\training-runs\rail-segmentation\l4r_winter_yolo26n_sanity\weights\best.pt --split test --exist-ok
```

Create RailGoerl24 drafts without treating missed detections as background:

```powershell
.\.venv-vision\Scripts\python.exe tools\rail_segmentation.py preannotate --model output\training-runs\rail-segmentation\l4r_winter_yolo26n_sanity\weights\best.pt
```

`draft_labels/` contains confidence-free YOLO segmentation labels that can be
corrected or imported into an annotation tool. `review_images/` contains visual
overlays. `review_manifest.csv` puts missed and low-confidence images first.
It also records whether the mask reaches the near field and contains the lower
image center. This is a coarse safety/review heuristic for an ego-track camera,
not a substitute for manual confirmation or camera calibration.
No empty label is written for a miss, because every selected image is expected
to contain a current track and a miss must not become a negative training sample.

## Results from 2026-08-05

L4R_NLB winter, one training epoch:

| Split | Images | Mask mAP50 | Mask mAP50-95 |
| --- | ---: | ---: | ---: |
| validation | 250 | 0.993 | 0.967 |
| temporal test block | 241 | 0.992 | 0.986 |

The test images are in a different temporal block, but all L4R data still comes
from the same acquisition route. These metrics prove the conversion and training
pipeline works; they do not prove RailGoerl24 generalization.

Zero-shot RailGoerl24 results at confidence 0.15:

| Split | Images | Drafts | Misses |
| --- | ---: | ---: | ---: |
| train | 136 | 71 | 65 |
| validation | 32 | 22 | 10 |
| test | 32 | 10 | 22 |
| **total** | **200** | **103** | **97** |

The detected masks are often useful on a clear current track, while turnouts,
occlusion, and strong viewpoint changes are common failure cases. More L4R-only
epochs are unlikely to close this domain gap. The next useful step is to correct
all 200 drafts/misses, fine-tune on the RailGoerl24 train split, use validation
for iteration, and keep the 32-image test split untouched until final evaluation.

## Fall comparison

The L4R_NLB fall set produced 1,634 usable samples. With the same model,
resolution, batch size, seed, confidence threshold, and one-epoch schedule, its
model produced 148 RailGoerl24 drafts versus 103 for winter. Visual review showed
that many extra fall detections selected a neighboring line at a turnout.

Using the coarse requirement that a mask reaches normalized `y >= 0.85` and
contains normalized `x = 0.5` in that near-field slice:

| Model | Raw drafts | Geometry-pass candidates |
| --- | ---: | ---: |
| winter | 103 | 99 |
| fall | 148 | 56 |
| union of both models | — | 120 |

Therefore fall improves raw recall but is not a safe replacement for winter.
The useful next baseline is multi-season training followed by correction and
fine-tuning on RailGoerl24 itself.
