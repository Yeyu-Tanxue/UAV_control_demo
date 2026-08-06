#!/usr/bin/env python3
"""Build and audit a Labelme workspace for RailGoerl24 rail polygons."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGES = (
    REPO_ROOT / "output/training-images/railgoerl24/batch_001_200/images"
)
DEFAULT_PREANNOTATIONS = REPO_ROOT / "output/preannotations/railgoerl24_l4r_v0"
DEFAULT_OUTPUT = (
    REPO_ROOT / "output/manual-annotations/railgoerl24_winter_labelme"
)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
SPLITS = ("train", "val", "test")


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def materialize_image(source: Path, destination: Path) -> None:
    if destination.exists():
        if destination.stat().st_size != source.stat().st_size:
            raise FileExistsError(f"Existing image differs in size: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def read_yolo_shapes(label_path: Path, width: int, height: int) -> list[dict]:
    if not label_path.is_file():
        return []
    shapes: list[dict] = []
    for line_number, line in enumerate(
        label_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        tokens = line.split()
        if not tokens:
            continue
        values = [float(value) for value in tokens[1:]]
        if len(values) < 6 or len(values) % 2:
            raise ValueError(f"Invalid polygon at {label_path}:{line_number}")
        points = [
            [round(values[index] * width, 3), round(values[index + 1] * height, 3)]
            for index in range(0, len(values), 2)
        ]
        shapes.append(
            {
                "label": "ego_track_area",
                "points": points,
                "group_id": None,
                "description": "winter model draft; verify and correct",
                "shape_type": "polygon",
                "flags": {},
                "mask": None,
            }
        )
    return shapes


def load_prediction_manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["image"]: row for row in csv.DictReader(handle)}


def prepare(args: argparse.Namespace) -> int:
    images_root = resolve_path(args.images_root)
    preannotations = resolve_path(args.preannotations)
    output = resolve_path(args.output)
    manifest_path = preannotations / "review_manifest.csv"
    if not images_root.is_dir():
        raise SystemExit(f"Image root does not exist: {images_root}")
    if not manifest_path.is_file():
        raise SystemExit(f"Prediction manifest does not exist: {manifest_path}")

    predictions = load_prediction_manifest(manifest_path)
    queue: list[dict[str, object]] = []
    created = skipped = 0
    for split in SPLITS:
        split_images = sorted(
            path
            for path in (images_root / split).iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        for image_path in split_images:
            relative_image = f"{split}/{image_path.name}"
            prediction = predictions.get(relative_image, {})
            destination_image = output / split / image_path.name
            destination_json = destination_image.with_suffix(".json")
            materialize_image(image_path, destination_image)

            with Image.open(image_path) as image:
                width, height = image.size
            draft_label = preannotations / "draft_labels" / split / f"{image_path.stem}.txt"
            shapes = read_yolo_shapes(draft_label, width, height)
            document = {
                "version": "7.0.4",
                "flags": {"reviewed": False},
                "shapes": shapes,
                "imagePath": image_path.name,
                "imageData": None,
                "imageHeight": height,
                "imageWidth": width,
            }
            if destination_json.exists() and not args.overwrite:
                skipped += 1
            else:
                destination_json.parent.mkdir(parents=True, exist_ok=True)
                destination_json.write_text(
                    json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                created += 1

            queue.append(
                {
                    "split": split,
                    "image": image_path.name,
                    "prediction_status": prediction.get("status", "unknown"),
                    "confidence": prediction.get("confidence", ""),
                    "near_field_contains_center": prediction.get(
                        "near_field_contains_center", ""
                    ),
                    "has_draft_polygon": bool(shapes),
                    "reviewed": False,
                }
            )

    priority = {"no_detection": 0, "draft": 1, "unknown": 2}
    split_order = {split: index for index, split in enumerate(SPLITS)}
    queue.sort(
        key=lambda row: (
            split_order[str(row["split"])],
            priority.get(str(row["prediction_status"]), 3),
            str(row["image"]),
        )
    )
    for index, row in enumerate(queue, start=1):
        row["review_order"] = index

    output.mkdir(parents=True, exist_ok=True)
    fields = [
        "review_order",
        "split",
        "image",
        "prediction_status",
        "confidence",
        "near_field_contains_center",
        "has_draft_polygon",
        "reviewed",
    ]
    with (output / "annotation_queue.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(queue)

    (output / "labels.txt").write_text("ego_track_area\n", encoding="utf-8")
    (output / "flags.txt").write_text("reviewed\n", encoding="utf-8")
    (output / "labelme-config.yaml").write_text(
        "auto_save: false\nstore_data: false\nkeep_prev: false\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(
        "# RailGoerl24 winter Labelme review\n\n"
        "Open `train` first. Correct or draw exactly one `ego_track_area` polygon, "
        "tick the image flag `reviewed`, then save. Do not rename images. Finish "
        "train, then val, and leave test until the final review pass.\n",
        encoding="utf-8",
    )
    (output.parent / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    print(f"Images prepared: {len(queue)}")
    print(f"JSON created: {created}; preserved: {skipped}")
    print(f"Workspace: {output}")
    return 0


def validate_document(path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"invalid_json:{exc}"]
    reviewed = document.get("flags", {}).get("reviewed") is True
    shapes = document.get("shapes", [])
    valid_shapes = [
        shape
        for shape in shapes
        if shape.get("label") == "ego_track_area"
        and shape.get("shape_type") == "polygon"
        and len(shape.get("points", [])) >= 3
    ]
    if reviewed and len(valid_shapes) != 1:
        errors.append(f"reviewed_requires_one_polygon:found_{len(valid_shapes)}")
    if any(shape.get("label") != "ego_track_area" for shape in shapes):
        errors.append("unexpected_label")
    return reviewed, errors


def status(args: argparse.Namespace) -> int:
    workspace = resolve_path(args.output)
    rows: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    for split in SPLITS:
        for path in sorted((workspace / split).glob("*.json")):
            reviewed, errors = validate_document(path)
            state = "invalid" if errors else "reviewed" if reviewed else "pending"
            counts[f"{split}:{state}"] += 1
            rows.append(
                {
                    "split": split,
                    "json": path.name,
                    "state": state,
                    "errors": ";".join(errors),
                }
            )
    with (workspace / "annotation_status.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=("split", "json", "state", "errors"))
        writer.writeheader()
        writer.writerows(rows)
    for split in SPLITS:
        reviewed = counts[f"{split}:reviewed"]
        pending = counts[f"{split}:pending"]
        invalid = counts[f"{split}:invalid"]
        print(f"{split}: reviewed={reviewed}, pending={pending}, invalid={invalid}")
    return 1 if any(key.endswith(":invalid") and value for key, value in counts.items()) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--images-root", default=str(DEFAULT_IMAGES))
    prepare_parser.add_argument("--preannotations", default=str(DEFAULT_PREANNOTATIONS))
    prepare_parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    prepare_parser.add_argument("--overwrite", action="store_true")
    prepare_parser.set_defaults(func=prepare)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    status_parser.set_defaults(func=status)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
