#!/usr/bin/env python3
"""Select and optionally materialize a deterministic rail-annotation batch."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Sequence

try:
    from tools.prepare_railgoerl24 import evenly_spaced_rows
except ModuleNotFoundError:  # Direct execution: python tools/select_rail_annotation_batch.py
    from prepare_railgoerl24 import evenly_spaced_rows


SPLIT_ORDER = {"train": 0, "val": 1, "test": 2}
SCENARIO_PRIORITY = {"normal": 0, "object_on_track": 1, "switch_review": 2}


def _number(row: dict[str, str], field: str) -> int:
    try:
        return int(row.get(field, "") or 0)
    except ValueError:
        return 0


def load_candidates(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "image_path",
        "annotation_path",
        "sequence_id",
        "frame_id",
        "split",
        "scenario_hint",
        "person_count",
        "bicycle_count",
    }
    if not rows:
        raise ValueError(f"Candidate file is empty: {path}")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Candidate file is missing columns: {sorted(missing)}")
    image_paths = [row["image_path"] for row in rows]
    if len(image_paths) != len(set(image_paths)):
        raise ValueError("Candidate file contains duplicate image paths")
    return rows


def _candidate_difficulty(row: dict[str, str]) -> tuple[int, int, int, int]:
    return (
        SCENARIO_PRIORITY.get(row.get("scenario_hint", "normal"), 0),
        _number(row, "person_count") + _number(row, "bicycle_count"),
        _number(row, "bicycle_count"),
        _number(row, "frame_id"),
    )


def _select_train(rows: list[dict[str, str]], quota: int) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["sequence_id"]].append(row)
    for sequence_rows in grouped.values():
        sequence_rows.sort(key=lambda row: (_number(row, "frame_id"), row["image_path"]))

    if quota < len(grouped):
        raise ValueError(
            f"Train quota {quota} cannot cover all {len(grouped)} training sequences"
        )
    if quota > len(rows):
        raise ValueError(f"Train quota {quota} exceeds {len(rows)} candidates")

    coverage_per_sequence = min(2, quota // len(grouped))
    selected: list[dict[str, str]] = []
    selected_paths: set[str] = set()
    for sequence in sorted(grouped):
        for row in evenly_spaced_rows(grouped[sequence], coverage_per_sequence):
            chosen = dict(row)
            chosen["selection_reason"] = "sequence_coverage"
            selected.append(chosen)
            selected_paths.add(chosen["image_path"])

    # Add at most one difficult sample per sequence in each round. This keeps
    # the extra quota diverse instead of filling it from one long sequence.
    while len(selected) < quota:
        remaining_by_sequence: dict[str, list[dict[str, str]]] = {}
        for sequence, sequence_rows in grouped.items():
            remaining = [row for row in sequence_rows if row["image_path"] not in selected_paths]
            if remaining:
                remaining_by_sequence[sequence] = sorted(
                    remaining,
                    key=lambda row: (_candidate_difficulty(row), row["image_path"]),
                    reverse=True,
                )
        if not remaining_by_sequence:
            raise ValueError("Not enough unique training candidates to fill the quota")
        ranked_sequences = sorted(
            remaining_by_sequence,
            key=lambda sequence: (
                _candidate_difficulty(remaining_by_sequence[sequence][0]),
                sequence,
            ),
            reverse=True,
        )
        for sequence in ranked_sequences:
            if len(selected) >= quota:
                break
            chosen = dict(remaining_by_sequence[sequence][0])
            chosen["selection_reason"] = "hard_case_extension"
            selected.append(chosen)
            selected_paths.add(chosen["image_path"])
    return selected


def _select_holdout(rows: list[dict[str, str]], quota: int) -> list[dict[str, str]]:
    if quota > len(rows):
        raise ValueError(f"Holdout quota {quota} exceeds {len(rows)} candidates")
    ordered = sorted(
        rows,
        key=lambda row: (row["sequence_id"], _number(row, "frame_id"), row["image_path"]),
    )
    chosen_rows = ordered if quota == len(ordered) else evenly_spaced_rows(ordered, quota)
    selected = []
    for row in chosen_rows:
        chosen = dict(row)
        chosen["selection_reason"] = "holdout_ground_truth"
        selected.append(chosen)
    return selected


def select_batch(
    candidates: list[dict[str, str]], quotas: dict[str, int]
) -> list[dict[str, str]]:
    by_split: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        by_split[row["split"]].append(row)

    selected = _select_train(by_split["train"], quotas["train"])
    selected.extend(_select_holdout(by_split["val"], quotas["val"]))
    selected.extend(_select_holdout(by_split["test"], quotas["test"]))
    selected.sort(
        key=lambda row: (
            SPLIT_ORDER[row["split"]],
            row["sequence_id"],
            _number(row, "frame_id"),
            row["image_path"],
        )
    )
    for index, row in enumerate(selected, start=1):
        original_name = Path(row["image_path"]).name
        row["batch_id"] = "railgoerl24_batch_001"
        row["batch_order"] = str(index)
        row["batch_image_path"] = f"images/{row['split']}/{index:03d}__{original_name}"
        row["annotation_mode"] = (
            "prelabel_then_review" if row["split"] == "train" else "manual_ground_truth"
        )
        row["annotation_status"] = "pending"
        row["exclude_reason"] = ""
    return selected


def _write_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    rows = list(rows)
    source_fields = list(rows[0])
    preferred = [
        "batch_id",
        "batch_order",
        "batch_image_path",
        "image_path",
        "annotation_path",
        "sequence_id",
        "frame_id",
        "split",
        "camera_height_m",
        "person_count",
        "bicycle_count",
        "scenario_hint",
        "selection_reason",
        "annotation_mode",
        "annotation_status",
        "exclude_reason",
    ]
    fieldnames = preferred + [field for field in source_fields if field not in preferred]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def materialize_images(
    selected: list[dict[str, str]], dataset_root: Path, output_dir: Path
) -> int:
    total_bytes = 0
    for row in selected:
        source = dataset_root / row["image_path"]
        destination = output_dir / row["batch_image_path"]
        if not source.is_file():
            raise FileNotFoundError(f"Selected source image is missing: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        total_bytes += destination.stat().st_size
    return total_bytes


def write_summary(
    output_dir: Path,
    selected: list[dict[str, str]],
    materialized_bytes: int,
) -> dict[str, object]:
    split_counts = Counter(row["split"] for row in selected)
    reason_counts = Counter(row["selection_reason"] for row in selected)
    scenario_counts = Counter(row["scenario_hint"] for row in selected)
    sequence_counts = {
        split: len({row["sequence_id"] for row in selected if row["split"] == split})
        for split in SPLIT_ORDER
    }
    summary: dict[str, object] = {
        "batch_id": "railgoerl24_batch_001",
        "image_count": len(selected),
        "split_counts": dict(split_counts),
        "sequence_counts": sequence_counts,
        "selection_reason_counts": dict(reason_counts),
        "scenario_counts": dict(scenario_counts),
        "materialized": materialized_bytes > 0,
        "materialized_bytes": materialized_bytes,
        "source_data_modified": False,
    }
    (output_dir / "batch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# RailGoerl24 首批200张标注集",
        "",
        "- train：136张，允许模型预标注后人工修正；",
        "- val：32张，完全人工确认，不参与训练；",
        "- test：32张，完全人工确认，不参与训练或伪标签迭代；",
        f"- 覆盖视频序列：train {sequence_counts['train']} / val {sequence_counts['val']} / test {sequence_counts['test']}；",
        f"- 图片副本大小：{materialized_bytes / 1024 / 1024:.1f} MiB。",
        "",
        "图片位于 `images/train`、`images/val`、`images/test`。文件名前的三位数字对应 `annotation_batch.csv` 中的 `batch_order`。",
        "标注 `ego_track_area` 多边形：只覆盖当前行驶股道两条内侧轨缘之间的区域。道岔走向不明确时不要猜测，改为 excluded 并填写原因。",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    rail_output = repo_root / "output" / "training-images" / "railgoerl24"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidates",
        type=Path,
        default=rail_output / "rail_annotation_candidates.csv",
    )
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path, default=rail_output / "batch_001_200"
    )
    parser.add_argument("--train", type=int, default=136)
    parser.add_argument("--val", type=int, default=32)
    parser.add_argument("--test", type=int, default=32)
    parser.add_argument(
        "--materialize",
        action="store_true",
        help="Copy selected images into the batch directory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    quotas = {"train": args.train, "val": args.val, "test": args.test}
    if any(quota < 0 for quota in quotas.values()):
        print("error: split quotas cannot be negative", file=sys.stderr)
        return 2
    try:
        candidates = load_candidates(args.candidates)
        selected = select_batch(candidates, quotas)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        _write_csv(args.output_dir / "annotation_batch.csv", selected)
        materialized_bytes = (
            materialize_images(selected, args.dataset_root, args.output_dir)
            if args.materialize
            else 0
        )
        summary = write_summary(args.output_dir, selected, materialized_bytes)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"Selected {summary['image_count']} images: "
        f"train={quotas['train']}, val={quotas['val']}, test={quotas['test']}"
    )
    print(f"Output: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
