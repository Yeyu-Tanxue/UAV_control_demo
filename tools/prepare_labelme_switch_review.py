#!/usr/bin/env python3
"""Build and audit a focused Labelme workspace for RailGoerl24 switches."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT.parent / "图像数据/Annotated_RGB_data"
DEFAULT_SEQUENCE_IMAGES = (
    DATA_ROOT / "imgs/2024-04-25_TUEV_Elchingen/Weichenstellung.mp4"
)
DEFAULT_SEQUENCE_PREANNOTATIONS = (
    REPO_ROOT / "output/preannotations/railgoerl24_switch_sequence_single_l4r_v0"
)
DEFAULT_BATCH_IMAGES = (
    REPO_ROOT / "output/training-images/railgoerl24/batch_001_200/images"
)
DEFAULT_BATCH_PREANNOTATIONS = (
    REPO_ROOT / "output/preannotations/railgoerl24_switches_single_l4r_v0"
)
DEFAULT_OUTPUT = (
    REPO_ROOT / "output/manual-annotations/railgoerl24_switch_labelme_batch_001"
)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


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


def read_detection_shapes(label_path: Path, width: int, height: int) -> list[dict]:
    """Convert YOLO detection boxes into Labelme rectangles."""
    if not label_path.is_file():
        return []
    shapes: list[dict] = []
    for line_number, line in enumerate(
        label_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        tokens = line.split()
        if not tokens:
            continue
        if len(tokens) != 5:
            raise ValueError(f"Invalid detection at {label_path}:{line_number}")
        class_id, x, y, box_width, box_height = [float(value) for value in tokens]
        if int(class_id) != 0:
            raise ValueError(f"Expected class 0 at {label_path}:{line_number}")
        left = max(0.0, (x - box_width / 2.0) * width)
        top = max(0.0, (y - box_height / 2.0) * height)
        right = min(float(width), (x + box_width / 2.0) * width)
        bottom = min(float(height), (y + box_height / 2.0) * height)
        if right <= left or bottom <= top:
            raise ValueError(f"Degenerate detection at {label_path}:{line_number}")
        shapes.append(
            {
                "label": "switch",
                "points": [
                    [round(left, 3), round(top, 3)],
                    [round(right, 3), round(bottom, 3)],
                ],
                "group_id": None,
                "description": "model draft; correct or delete",
                "shape_type": "rectangle",
                "flags": {},
                "mask": None,
            }
        )
    return shapes


def evenly_spaced(items: list[dict], count: int) -> list[dict]:
    if count <= 0 or not items:
        return []
    if count >= len(items):
        return list(items)
    if count == 1:
        return [items[len(items) // 2]]
    indices = [round(index * (len(items) - 1) / (count - 1)) for index in range(count)]
    return [items[index] for index in indices]


def _sequence_key(image: str) -> str:
    stem = Path(image).stem
    if "__" in stem:
        stem = stem.split("__", 1)[1]
    return stem.rsplit("_", 1)[0]


def diverse_sample(rows: list[dict], count: int) -> list[dict]:
    """Round-robin across sequences so one long clip cannot dominate a batch."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[_sequence_key(str(row["image"]))].append(row)
    selected: list[dict] = []
    depth = 0
    while len(selected) < count:
        added = False
        for key in sorted(groups):
            values = groups[key]
            if depth < len(values):
                selected.append(values[depth])
                added = True
                if len(selected) == count:
                    return selected
        if not added:
            break
        depth += 1
    return selected


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: str) -> float:
    return float(value) if value else -1.0


def select_queue(
    sequence_rows: list[dict[str, str]],
    batch_rows: list[dict[str, str]],
    switch_count: int,
    hard_negative_count: int,
    clean_negative_count: int,
) -> list[dict[str, str]]:
    sequence = evenly_spaced(sorted(sequence_rows, key=lambda row: row["image"]), switch_count)
    non_switch = [row for row in batch_rows if "Weichenstellung" not in row["image"]]
    hard_candidates = sorted(
        (row for row in non_switch if int(row["detection_count"]) > 0),
        key=lambda row: (-_float(row["max_confidence"]), row["image"]),
    )
    hard = diverse_sample(hard_candidates, hard_negative_count)
    hard_images = {row["image"] for row in hard}
    clean_candidates = [
        row
        for row in non_switch
        if int(row["detection_count"]) == 0 and row["image"] not in hard_images
    ]
    clean = diverse_sample(clean_candidates, clean_negative_count)

    queue: list[dict[str, str]] = []
    for category, rows in (
        ("switch_sequence", sequence),
        ("hard_negative", hard),
        ("clean_negative", clean),
    ):
        for row in rows:
            queue.append({**row, "category": category})
    return queue


def _source_and_label(
    row: dict[str, str],
    sequence_images: Path,
    sequence_preannotations: Path,
    batch_images: Path,
    batch_preannotations: Path,
) -> tuple[Path, Path]:
    if row["category"] == "switch_sequence":
        source = sequence_images / row["image"]
        label = sequence_preannotations / row["draft_label"]
    else:
        source = batch_images / row["image"]
        label = batch_preannotations / row["draft_label"]
    return source, label


def prepare(args: argparse.Namespace) -> int:
    sequence_images = resolve_path(args.sequence_images)
    sequence_preannotations = resolve_path(args.sequence_preannotations)
    batch_images = resolve_path(args.batch_images)
    batch_preannotations = resolve_path(args.batch_preannotations)
    output = resolve_path(args.output)
    for path in (sequence_images, sequence_preannotations, batch_images, batch_preannotations):
        if not path.exists():
            raise SystemExit(f"Required path does not exist: {path}")

    sequence_rows = load_manifest(sequence_preannotations / "review_manifest.csv")
    batch_rows = load_manifest(batch_preannotations / "review_manifest.csv")
    queue = select_queue(
        sequence_rows,
        batch_rows,
        args.switch_count,
        args.hard_negative_count,
        args.clean_negative_count,
    )
    images_output = output / "images"
    created = preserved = 0
    queue_rows: list[dict[str, object]] = []
    for review_order, row in enumerate(queue, start=1):
        source, label_path = _source_and_label(
            row,
            sequence_images,
            sequence_preannotations,
            batch_images,
            batch_preannotations,
        )
        if not source.is_file() or source.suffix.lower() not in IMAGE_SUFFIXES:
            raise FileNotFoundError(f"Source image does not exist: {source}")
        workspace_name = f"{review_order:03d}__{row['category']}__{source.name}"
        destination_image = images_output / workspace_name
        destination_json = destination_image.with_suffix(".json")
        materialize_image(source, destination_image)
        with Image.open(source) as image:
            width, height = image.size
        shapes = read_detection_shapes(label_path, width, height)
        document = {
            "version": "7.0.4",
            "flags": {"reviewed": False, "uncertain": False},
            "shapes": shapes,
            "imagePath": workspace_name,
            "imageData": None,
            "imageHeight": height,
            "imageWidth": width,
        }
        if destination_json.exists() and not args.overwrite:
            preserved += 1
        else:
            destination_json.parent.mkdir(parents=True, exist_ok=True)
            destination_json.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            created += 1
        queue_rows.append(
            {
                "review_order": review_order,
                "category": row["category"],
                "workspace_image": f"images/{workspace_name}",
                "source_image": str(source),
                "model_detection_count": row["detection_count"],
                "max_confidence": row["max_confidence"],
                "has_draft_box": bool(shapes),
                "reviewed": False,
            }
        )

    output.mkdir(parents=True, exist_ok=True)
    fields = list(queue_rows[0])
    with (output / "annotation_queue.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(queue_rows)
    (output / "labels.txt").write_text("switch\n", encoding="utf-8")
    (output / "flags.txt").write_text("reviewed\nuncertain\n", encoding="utf-8")
    (output / "labelme-config.yaml").write_text(
        "auto_save: false\nstore_data: false\nkeep_prev: false\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(
        "# RailGoerl24 switch Labelme review\n\n"
        "Open the `images` folder in Labelme and review files in numeric order. "
        "Correct or delete every draft rectangle, and draw a `switch` rectangle "
        "around every visible turnout. A confirmed non-switch image must contain "
        "zero rectangles. Tick `reviewed` only after checking the whole image; tick "
        "`uncertain` when the turnout is too distant or ambiguous. Save without "
        "renaming the image or JSON file.\n",
        encoding="utf-8",
    )
    ignore = output.parent / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n!.gitignore\n", encoding="utf-8")
    counts = Counter(row["category"] for row in queue_rows)
    print(f"Images prepared: {len(queue_rows)}")
    for category in ("switch_sequence", "hard_negative", "clean_negative"):
        print(f"{category}: {counts[category]}")
    print(f"JSON created: {created}; preserved: {preserved}")
    print(f"Workspace: {output}")
    return 0


def validate_document(path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"invalid_json:{exc}"]
    reviewed = document.get("flags", {}).get("reviewed") is True
    for shape in document.get("shapes", []):
        if shape.get("label") != "switch":
            errors.append("unexpected_label")
        if shape.get("shape_type") != "rectangle" or len(shape.get("points", [])) != 2:
            errors.append("switch_requires_rectangle")
    return reviewed, sorted(set(errors))


def status(args: argparse.Namespace) -> int:
    workspace = resolve_path(args.output)
    rows: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for path in sorted((workspace / "images").glob("*.json")):
        reviewed, errors = validate_document(path)
        state = "invalid" if errors else "reviewed" if reviewed else "pending"
        counts[state] += 1
        rows.append({"json": path.name, "state": state, "errors": ";".join(errors)})
    with (workspace / "annotation_status.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=("json", "state", "errors"))
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"reviewed={counts['reviewed']}, pending={counts['pending']}, "
        f"invalid={counts['invalid']}"
    )
    return 1 if counts["invalid"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--sequence-images", default=str(DEFAULT_SEQUENCE_IMAGES))
    prepare_parser.add_argument(
        "--sequence-preannotations", default=str(DEFAULT_SEQUENCE_PREANNOTATIONS)
    )
    prepare_parser.add_argument("--batch-images", default=str(DEFAULT_BATCH_IMAGES))
    prepare_parser.add_argument(
        "--batch-preannotations", default=str(DEFAULT_BATCH_PREANNOTATIONS)
    )
    prepare_parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    prepare_parser.add_argument("--switch-count", type=int, default=30)
    prepare_parser.add_argument("--hard-negative-count", type=int, default=30)
    prepare_parser.add_argument("--clean-negative-count", type=int, default=20)
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
