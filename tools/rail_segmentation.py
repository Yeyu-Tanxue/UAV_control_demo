#!/usr/bin/env python3
"""Train, evaluate, and create reviewable rail-area segmentation drafts."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPO_ROOT / "output/training-images/l4r_nlb_winter_yolo/dataset.yaml"
DEFAULT_RUNS = REPO_ROOT / "output/training-runs/rail-segmentation"
DEFAULT_RAILGOERL = (
    REPO_ROOT
    / "output/training-images/railgoerl24/batch_001_200/images"
)


def _ultralytics_yolo():
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "ultralytics is not installed. Follow docs/vision/rail-segmentation-baseline.md"
        ) from exc
    return YOLO


def _path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _common_kwargs(args: argparse.Namespace) -> dict[str, object]:
    return {
        "imgsz": args.imgsz,
        "batch": args.batch,
        "device": args.device,
        "workers": args.workers,
    }


def train(args: argparse.Namespace) -> None:
    YOLO = _ultralytics_yolo()
    data = _path(args.data)
    if not data.is_file():
        raise SystemExit(f"Dataset YAML does not exist: {data}")
    YOLO(args.model).train(
        data=str(data),
        epochs=args.epochs,
        project=str(_path(args.project)),
        name=args.name,
        exist_ok=args.exist_ok,
        seed=args.seed,
        deterministic=True,
        amp=True,
        plots=True,
        **_common_kwargs(args),
    )


def validate(args: argparse.Namespace) -> None:
    YOLO = _ultralytics_yolo()
    model = _path(args.model)
    data = _path(args.data)
    if not model.is_file():
        raise SystemExit(f"Model does not exist: {model}")
    if not data.is_file():
        raise SystemExit(f"Dataset YAML does not exist: {data}")
    YOLO(str(model)).val(
        data=str(data),
        split=args.split,
        project=str(_path(args.project)),
        name=args.name,
        exist_ok=args.exist_ok,
        plots=True,
        **_common_kwargs(args),
    )


def _image_groups(source: Path) -> Iterable[tuple[str, Path]]:
    split_dirs = [(split, source / split) for split in ("train", "val", "test")]
    existing = [(split, path) for split, path in split_dirs if path.is_dir()]
    return existing or [("all", source)]


def _write_segmentation_label(path: Path, class_id: int, polygon) -> None:
    coordinates = " ".join(f"{float(value):.6f}" for point in polygon for value in point)
    path.write_text(f"{class_id} {coordinates}\n", encoding="utf-8")


def preannotate(args: argparse.Namespace) -> None:
    YOLO = _ultralytics_yolo()
    model_path = _path(args.model)
    source = _path(args.source)
    output = _path(args.output)
    if not model_path.is_file():
        raise SystemExit(f"Model does not exist: {model_path}")
    if not source.is_dir():
        raise SystemExit(f"Image source does not exist: {source}")

    model = YOLO(str(model_path))
    rows: list[dict[str, object]] = []
    for split, image_dir in _image_groups(source):
        label_dir = output / "draft_labels" / split
        review_dir = output / "review_images" / split
        label_dir.mkdir(parents=True, exist_ok=True)
        review_dir.mkdir(parents=True, exist_ok=True)

        results = model.predict(
            source=str(image_dir),
            imgsz=args.imgsz,
            conf=args.conf,
            device=args.device,
            max_det=1,
            stream=True,
            verbose=args.verbose,
        )
        for result in results:
            image_path = Path(result.path)
            label_path = label_dir / f"{image_path.stem}.txt"
            review_path = review_dir / image_path.name
            result.save(filename=str(review_path))

            detected = result.masks is not None and result.boxes is not None and len(result.boxes) > 0
            confidence = float(result.boxes.conf[0].item()) if detected else None
            if detected:
                class_id = int(result.boxes.cls[0].item())
                polygon = result.masks.xyn[0]
                _write_segmentation_label(label_path, class_id, polygon)

            if not detected:
                priority = "high"
                status = "no_detection"
            elif confidence is not None and confidence < args.review_conf:
                priority = "high"
                status = "draft"
            else:
                priority = "normal"
                status = "draft"

            rows.append(
                {
                    "split": split,
                    "image": image_path.relative_to(source).as_posix(),
                    "status": status,
                    "confidence": "" if confidence is None else f"{confidence:.6f}",
                    "review_priority": priority,
                    "draft_label": (
                        label_path.relative_to(output).as_posix() if detected else ""
                    ),
                    "review_image": review_path.relative_to(output).as_posix(),
                }
            )

    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "review_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    detected_count = sum(row["status"] == "draft" for row in rows)
    print(f"Images: {len(rows)}")
    print(f"Draft labels: {detected_count}")
    print(f"No detection: {len(rows) - detected_count}")
    print(f"Review manifest: {manifest}")


def _add_runtime_args(parser: argparse.ArgumentParser, *, batch: int = 4) -> None:
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=batch)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_parser = subparsers.add_parser("train", help="Train the L4R rail-area model")
    train_parser.add_argument("--model", default="yolo26n-seg.pt")
    train_parser.add_argument("--data", default=str(DEFAULT_DATA))
    train_parser.add_argument("--epochs", type=int, default=10)
    train_parser.add_argument("--project", default=str(DEFAULT_RUNS))
    train_parser.add_argument("--name", default="l4r_winter_yolo26n")
    train_parser.add_argument("--seed", type=int, default=20260805)
    train_parser.add_argument("--exist-ok", action="store_true")
    _add_runtime_args(train_parser)
    train_parser.set_defaults(func=train)

    val_parser = subparsers.add_parser("validate", help="Evaluate a trained checkpoint")
    val_parser.add_argument("--model", required=True)
    val_parser.add_argument("--data", default=str(DEFAULT_DATA))
    val_parser.add_argument("--split", choices=("val", "test"), default="test")
    val_parser.add_argument("--project", default=str(DEFAULT_RUNS))
    val_parser.add_argument("--name", default="l4r_winter_yolo26n_test")
    val_parser.add_argument("--exist-ok", action="store_true")
    _add_runtime_args(val_parser)
    val_parser.set_defaults(func=validate)

    pre_parser = subparsers.add_parser(
        "preannotate", help="Create clean YOLO draft labels and a review queue"
    )
    pre_parser.add_argument("--model", required=True)
    pre_parser.add_argument("--source", default=str(DEFAULT_RAILGOERL))
    pre_parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "output/preannotations/railgoerl24_l4r_v0"),
    )
    pre_parser.add_argument("--imgsz", type=int, default=640)
    pre_parser.add_argument("--conf", type=float, default=0.15)
    pre_parser.add_argument("--review-conf", type=float, default=0.50)
    pre_parser.add_argument("--device", default="0")
    pre_parser.add_argument("--verbose", action="store_true")
    pre_parser.set_defaults(func=preannotate)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
