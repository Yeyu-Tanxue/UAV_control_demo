#!/usr/bin/env python3
"""Train, evaluate, and preannotate railway switches with YOLO detection."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPO_ROOT / "output/training-images/l4r_nlb_switches_yolo/dataset.yaml"
DEFAULT_RUNS = REPO_ROOT / "output/training-runs/switch-detection"
DEFAULT_RAILGOERL = REPO_ROOT / "output/training-images/railgoerl24/batch_001_200/images"


def _yolo():
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("ultralytics is not installed in the active Python environment") from exc
    return YOLO


def _path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _runtime(args: argparse.Namespace) -> dict[str, object]:
    return {"imgsz": args.imgsz, "batch": args.batch, "device": args.device, "workers": args.workers}


def train(args: argparse.Namespace) -> None:
    data = _path(args.data)
    if not data.is_file():
        raise SystemExit(f"Dataset YAML does not exist: {data}")
    _yolo()(str(_path(args.model)) if _path(args.model).is_file() else args.model).train(
        data=str(data), epochs=args.epochs, project=str(_path(args.project)), name=args.name,
        exist_ok=args.exist_ok, seed=args.seed, deterministic=True, amp=True, plots=True,
        **_runtime(args),
    )


def validate(args: argparse.Namespace) -> None:
    model = _path(args.model)
    data = _path(args.data)
    if not model.is_file() or not data.is_file():
        raise SystemExit(f"Missing model or data: {model}, {data}")
    _yolo()(str(model)).val(
        data=str(data), split=args.split, project=str(_path(args.project)), name=args.name,
        exist_ok=args.exist_ok, plots=True, **_runtime(args),
    )


def _groups(source: Path):
    groups = [(name, source / name) for name in ("train", "val", "test")]
    existing = [(name, path) for name, path in groups if path.is_dir()]
    return existing or [("all", source)]


def _class_agnostic_nms(
    xyxy: list[list[float]], confidences: list[float], iou_threshold: float
) -> list[int]:
    """Return confidence-sorted indices after suppressing overlaps across classes."""

    def iou(first: list[float], second: list[float]) -> float:
        left = max(first[0], second[0])
        top = max(first[1], second[1])
        right = min(first[2], second[2])
        bottom = min(first[3], second[3])
        intersection = max(0.0, right - left) * max(0.0, bottom - top)
        first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
        second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
        union = first_area + second_area - intersection
        return intersection / union if union > 0.0 else 0.0

    kept: list[int] = []
    for index in sorted(range(len(confidences)), key=confidences.__getitem__, reverse=True):
        if all(iou(xyxy[index], xyxy[other]) <= iou_threshold for other in kept):
            kept.append(index)
    return kept


def _is_fork_name(name: str) -> bool:
    return name == "fork" or name.startswith("fork_")


def preannotate(args: argparse.Namespace) -> None:
    model_path, source, output = _path(args.model), _path(args.source), _path(args.output)
    if not model_path.is_file() or not source.is_dir():
        raise SystemExit(f"Missing model or source: {model_path}, {source}")
    model = _yolo()(str(model_path))
    rows: list[dict[str, object]] = []
    for split, image_dir in _groups(source):
        label_dir = output / "draft_labels" / split
        review_dir = output / "review_images" / split
        label_dir.mkdir(parents=True, exist_ok=True)
        review_dir.mkdir(parents=True, exist_ok=True)
        results = model.predict(
            source=str(image_dir), imgsz=args.imgsz, conf=args.conf, device=args.device,
            max_det=args.max_det, stream=True, verbose=args.verbose,
        )
        for result in results:
            image_path = Path(result.path)
            label_path = label_dir / f"{image_path.stem}.txt"
            review_path = review_dir / image_path.name
            raw_detection_count = len(result.boxes) if result.boxes is not None else 0
            if result.boxes is not None and raw_detection_count:
                keep = _class_agnostic_nms(
                    result.boxes.xyxy.cpu().tolist(),
                    result.boxes.conf.cpu().tolist(),
                    args.nms_iou,
                )
                result.boxes = result.boxes[keep]
            result.save(filename=str(review_path))
            lines: list[str] = []
            detections: list[str] = []
            confidences: list[float] = []
            if result.boxes is not None:
                for box in result.boxes:
                    class_id = int(box.cls.item())
                    x, y, width, height = [float(value) for value in box.xywhn[0].tolist()]
                    confidence = float(box.conf.item())
                    lines.append(f"{class_id} {x:.6f} {y:.6f} {width:.6f} {height:.6f}\n")
                    detections.append(str(result.names[class_id]))
                    confidences.append(confidence)
            label_path.write_text("".join(lines), encoding="utf-8")
            fork_detected = any(_is_fork_name(name) for name in detections)
            switch_detected = bool(detections)
            rows.append({
                "split": split,
                "image": image_path.relative_to(source).as_posix(),
                "raw_detection_count": raw_detection_count,
                "detection_count": len(detections),
                "suppressed_count": raw_detection_count - len(detections),
                "classes": ";".join(detections),
                "max_confidence": f"{max(confidences):.6f}" if confidences else "",
                "fork_detected": fork_detected,
                "switch_detected": switch_detected,
                "control_action": "slow_or_hover_and_select_branch" if switch_detected else "continue_track_following",
                "review_priority": "high" if switch_detected else "normal",
                "draft_label": label_path.relative_to(output).as_posix(),
                "review_image": review_path.relative_to(output).as_posix(),
            })
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "review_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Images: {len(rows)}")
    print(f"Images with detections: {sum(int(row['detection_count']) > 0 for row in rows)}")
    print(f"Images with fork detections: {sum(row['fork_detected'] is True for row in rows)}")
    print(f"Images with switch-event detections: {sum(row['switch_detected'] is True for row in rows)}")
    print(f"Review manifest: {manifest}")


def _runtime_args(parser: argparse.ArgumentParser, batch: int = 4) -> None:
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=batch)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    train_parser = sub.add_parser("train")
    train_parser.add_argument("--model", default="yolo26n.pt")
    train_parser.add_argument("--data", default=str(DEFAULT_DATA))
    train_parser.add_argument("--epochs", type=int, default=10)
    train_parser.add_argument("--project", default=str(DEFAULT_RUNS))
    train_parser.add_argument("--name", default="l4r_multiseason_yolo26n")
    train_parser.add_argument("--seed", type=int, default=20260805)
    train_parser.add_argument("--exist-ok", action="store_true")
    _runtime_args(train_parser)
    train_parser.set_defaults(func=train)

    val_parser = sub.add_parser("validate")
    val_parser.add_argument("--model", required=True)
    val_parser.add_argument("--data", default=str(DEFAULT_DATA))
    val_parser.add_argument("--split", choices=("val", "test"), default="test")
    val_parser.add_argument("--project", default=str(DEFAULT_RUNS))
    val_parser.add_argument("--name", default="l4r_multiseason_yolo26n_test")
    val_parser.add_argument("--exist-ok", action="store_true")
    _runtime_args(val_parser)
    val_parser.set_defaults(func=validate)

    pre_parser = sub.add_parser("preannotate")
    pre_parser.add_argument("--model", required=True)
    pre_parser.add_argument("--source", default=str(DEFAULT_RAILGOERL))
    pre_parser.add_argument("--output", default=str(REPO_ROOT / "output/preannotations/railgoerl24_switches_l4r_v0"))
    pre_parser.add_argument("--imgsz", type=int, default=960)
    pre_parser.add_argument("--conf", type=float, default=0.15)
    pre_parser.add_argument("--max-det", type=int, default=10)
    pre_parser.add_argument("--nms-iou", type=float, default=0.50)
    pre_parser.add_argument("--device", default="0")
    pre_parser.add_argument("--verbose", action="store_true")
    pre_parser.set_defaults(func=preannotate)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
