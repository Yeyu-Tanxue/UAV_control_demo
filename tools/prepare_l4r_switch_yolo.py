#!/usr/bin/env python3
"""Convert multiple L4R_NLB seasons into a YOLO railway-switch dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

try:
    from tools.prepare_l4r_nlb_yolo import frame_number
except ModuleNotFoundError:  # Direct execution from tools/.
    from prepare_l4r_nlb_yolo import frame_number


WIDTH = 1920
HEIGHT = 1080
SPLIT_RATIOS = {"train": 0.80, "val": 0.10, "test": 0.10}
CLASS_NAMES = (
    "fork_left",
    "fork_right",
    "fork_unknown",
    "merge_left",
    "merge_right",
    "merge_unknown",
)
CLASS_IDS = {name: index for index, name in enumerate(CLASS_NAMES)}
KIND_CLASS_NAMES = ("fork", "merge")
SINGLE_CLASS_NAMES = ("switch",)


def _output_class_id(class_id: int, class_mode: str) -> int:
    if class_mode == "detailed":
        return class_id
    if class_mode == "kind":
        return int(class_id >= 3)
    return 0


def _resolve_source(path: Path) -> Path:
    path = path.expanduser().resolve()
    if (path / "images").is_dir() and (path / "annotations").is_dir():
        return path
    candidates = [
        child
        for child in path.iterdir()
        if child.is_dir()
        and (child / "images").is_dir()
        and (child / "annotations").is_dir()
    ] if path.is_dir() else []
    if len(candidates) == 1:
        return candidates[0]
    raise FileNotFoundError(
        f"Expected images/ and annotations/ below {path}, or below one direct child"
    )


def _parse_sources(values: Sequence[str]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--source must use SEASON=PATH: {value}")
        season, raw_path = value.split("=", 1)
        season = season.strip().lower()
        if not season or season in sources:
            raise ValueError(f"Missing or duplicate season in --source: {value}")
        sources[season] = _resolve_source(Path(raw_path))
    if not sources:
        raise ValueError("At least one --source SEASON=PATH is required")
    return sources


def _switch_box(
    switch: object, width: int, height: int
) -> tuple[int, tuple[float, float, float, float], str] | tuple[None, None, str]:
    if not isinstance(switch, dict):
        return None, None, "invalid_switch"
    kind = str(switch.get("kind", "")).strip().lower()
    direction = str(switch.get("direction", "unknown")).strip().lower() or "unknown"
    class_name = f"{kind}_{direction}"
    if class_name not in CLASS_IDS:
        return None, None, f"unsupported_class_{class_name}"
    marks = switch.get("marks")
    if not isinstance(marks, list) or len(marks) != 2:
        return None, None, "invalid_marks"
    try:
        xs = [float(point["x"]) for point in marks if isinstance(point, dict)]
        ys = [float(point["y"]) for point in marks if isinstance(point, dict)]
    except (KeyError, TypeError, ValueError):
        return None, None, "invalid_marks"
    if len(xs) != 2 or len(ys) != 2:
        return None, None, "invalid_marks"
    x1 = max(0.0, min(float(width - 1), min(xs)))
    x2 = max(0.0, min(float(width - 1), max(xs)))
    y1 = max(0.0, min(float(height - 1), min(ys)))
    y2 = max(0.0, min(float(height - 1), max(ys)))
    if x2 - x1 < 2.0 or y2 - y1 < 2.0:
        return None, None, "degenerate_box"
    return CLASS_IDS[class_name], (x1, y1, x2, y2), "usable"


def _yolo_line(
    class_id: int, box: tuple[float, float, float, float], width: int, height: int
) -> str:
    x1, y1, x2, y2 = box
    return (
        f"{class_id} {(x1 + x2) / (2 * width):.6f} "
        f"{(y1 + y2) / (2 * height):.6f} {(x2 - x1) / width:.6f} "
        f"{(y2 - y1) / height:.6f}\n"
    )


def _materialize(source: Path, destination: Path, mode: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.stat().st_size != source.stat().st_size:
            raise FileExistsError(f"Existing destination differs in size: {destination}")
        return
    if mode == "hardlink":
        try:
            os.link(source, destination)
            return
        except OSError:
            shutil.copy2(source, destination)
            return
    shutil.copy2(source, destination)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def _assign_stratified_blocks(
    block_stats: dict[str, Counter[str]], seed: int
) -> dict[str, str]:
    """Keep temporal blocks intact while balancing images and switch classes."""

    splits = tuple(SPLIT_RATIOS)
    block_total = len(block_stats)
    capacities = {
        "val": max(1, round(block_total * SPLIT_RATIOS["val"])),
        "test": max(1, round(block_total * SPLIT_RATIOS["test"])),
    }
    capacities["train"] = block_total - capacities["val"] - capacities["test"]
    metrics = ("images", "positive_images", *CLASS_NAMES)
    totals = Counter[str]()
    for stats in block_stats.values():
        totals.update(stats)
    targets = {
        split: {metric: totals[metric] * SPLIT_RATIOS[split] for metric in metrics}
        for split in splits
    }
    assigned = {split: Counter[str]() for split in splits}
    block_counts: Counter[str] = Counter()
    result: dict[str, str] = {}

    def tie_breaker(block: str) -> str:
        return hashlib.sha256(f"{seed}:{block}".encode()).hexdigest()

    ordered = sorted(
        block_stats,
        key=lambda block: (
            -block_stats[block]["positive_images"],
            -sum(block_stats[block][name] for name in CLASS_NAMES),
            -block_stats[block]["images"],
            tie_breaker(block),
        ),
    )
    for block in ordered:
        candidates = [split for split in splits if block_counts[split] < capacities[split]]

        def score(split: str) -> tuple[float, float, int]:
            metric_error = 0.0
            for target_split in splits:
                for metric in metrics:
                    value = assigned[target_split][metric]
                    if target_split == split:
                        value += block_stats[block][metric]
                    metric_error += abs(value - targets[target_split][metric]) / max(
                        targets[target_split][metric], 1.0
                    )
            remaining = (capacities[split] - block_counts[split]) / max(
                capacities[split], 1
            )
            return metric_error, -remaining, splits.index(split)

        chosen = min(candidates, key=score)
        result[block] = chosen
        assigned[chosen].update(block_stats[block])
        block_counts[chosen] += 1
    return result


def _write_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    fields = [
        "season", "stem", "frame_id", "temporal_block", "split", "status",
        "exclude_reason", "source_image", "source_annotation", "yolo_image",
        "yolo_label", "switch_count", "usable_switch_count", "classes",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def prepare(
    sources: dict[str, Path],
    output: Path,
    block_size: int,
    seed: int,
    materialize_mode: str,
    class_mode: str = "detailed",
) -> dict[str, object]:
    output_class_names = {
        "detailed": CLASS_NAMES,
        "kind": KIND_CLASS_NAMES,
        "single": SINGLE_CLASS_NAMES,
    }[class_mode]
    rows: list[dict[str, object]] = []
    class_counts: Counter[str] = Counter()
    invalid_counts: Counter[str] = Counter()
    season_counts: Counter[str] = Counter()
    box_widths: list[float] = []
    box_heights: list[float] = []
    block_stats: dict[str, Counter[str]] = defaultdict(Counter)
    raw_switch_count = 0

    for season, source in sorted(sources.items()):
        images = {path.stem: path for path in (source / "images").glob("*.png")}
        annotations = {
            path.stem: path for path in (source / "annotations").glob("*.json")
        }
        for stem in sorted(annotations, key=frame_number):
            annotation_path = annotations[stem]
            image_path = images.get(stem)
            base = {
                "season": season,
                "stem": stem,
                "frame_id": frame_number(stem),
                "source_image": str(image_path) if image_path else "",
                "source_annotation": str(annotation_path),
            }
            if image_path is None:
                rows.append({**base, "status": "excluded", "exclude_reason": "missing_image"})
                continue
            try:
                data = json.loads(annotation_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                rows.append({**base, "status": "excluded", "exclude_reason": "json_parse_error"})
                continue
            switches = data.get("switches", {})
            if not isinstance(switches, dict):
                rows.append({**base, "status": "excluded", "exclude_reason": "invalid_switches"})
                continue
            raw_switch_count += len(switches)
            labels: list[tuple[int, tuple[float, float, float, float]]] = []
            seen_labels: set[tuple[int, tuple[float, float, float, float]]] = set()
            names: list[str] = []
            assignment_names: list[str] = []
            for switch in switches.values():
                class_id, box, reason = _switch_box(switch, WIDTH, HEIGHT)
                if class_id is None or box is None:
                    invalid_counts[reason] += 1
                    continue
                name = CLASS_NAMES[class_id]
                assignment_names.append(name)
                label = (class_id, box)
                if label in seen_labels:
                    invalid_counts["duplicate_box"] += 1
                    continue
                seen_labels.add(label)
                labels.append((class_id, box))
                names.append(name)
                class_counts[name] += 1
                box_widths.append(box[2] - box[0])
                box_heights.append(box[3] - box[1])
            block = int(base["frame_id"]) // block_size
            block_key = f"{season}:block_{block:04d}"
            block_stats[block_key]["images"] += 1
            if assignment_names:
                block_stats[block_key]["positive_images"] += 1
            for name in assignment_names:
                block_stats[block_key][name] += 1
            season_counts[season] += 1
            rows.append(
                {
                    **base,
                    "status": "usable",
                    "exclude_reason": "",
                    "temporal_block": block,
                    "switch_count": len(switches),
                    "usable_switch_count": len(labels),
                    "classes": json.dumps(names, ensure_ascii=False),
                    "labels": labels,
                    "block_key": block_key,
                }
            )

    assignments = _assign_stratified_blocks(block_stats, seed)
    output.mkdir(parents=True, exist_ok=True)
    (output / ".gitignore").write_text("/images/\n/labels/\n", encoding="utf-8")
    split_counts: Counter[str] = Counter()
    positive_counts: Counter[str] = Counter()
    split_class_counts: dict[str, Counter[str]] = defaultdict(Counter)
    output_class_counts: Counter[str] = Counter()
    split_blocks: dict[str, set[str]] = defaultdict(set)
    expected: dict[str, set[str]] = defaultdict(set)
    collapsed_duplicate_boxes = 0

    for row in rows:
        if row["status"] != "usable":
            row.update(split="", yolo_image="", yolo_label="")
            continue
        split = assignments[str(row.pop("block_key"))]
        output_stem = f"{row['season']}__{row['stem']}"
        image_rel = Path("images") / split / f"{output_stem}.png"
        label_rel = Path("labels") / split / f"{output_stem}.txt"
        _materialize(Path(str(row["source_image"])), output / image_rel, materialize_mode)
        label_path = output / label_rel
        label_path.parent.mkdir(parents=True, exist_ok=True)
        labels = row.pop("labels")
        output_labels = list(
            dict.fromkeys(
                (_output_class_id(class_id, class_mode), box)
                for class_id, box in labels
            )
        )
        collapsed_duplicate_boxes += len(labels) - len(output_labels)
        label_path.write_text(
            "".join(
                _yolo_line(class_id, box, WIDTH, HEIGHT)
                for class_id, box in output_labels
            ),
            encoding="utf-8",
        )
        row.update(
            split=split,
            yolo_image=PurePosixPath(image_rel).as_posix(),
            yolo_label=PurePosixPath(label_rel).as_posix(),
        )
        split_counts[split] += 1
        positive_counts[split] += bool(output_labels)
        for class_id, _ in output_labels:
            class_name = output_class_names[class_id]
            split_class_counts[split][class_name] += 1
            output_class_counts[class_name] += 1
        split_blocks[split].add(f"{row['season']}:{row['temporal_block']}")
        expected[split].add(output_stem)

    removed = 0
    for category, suffix in (("images", ".png"), ("labels", ".txt")):
        for split in ("train", "val", "test"):
            folder = output / category / split
            if not folder.is_dir():
                continue
            for path in folder.glob(f"*{suffix}"):
                if path.stem not in expected[split]:
                    path.unlink()
                    removed += 1

    _write_csv(output / "manifest.csv", rows)
    yaml_lines = ["train: images/train", "val: images/val", "test: images/test", "names:"]
    yaml_lines.extend(f"  {index}: {name}" for index, name in enumerate(output_class_names))
    (output / "dataset.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")

    report: dict[str, object] = {
        "label_definition": "L4R_NLB switch bounding boxes",
        "class_mode": class_mode,
        "sources": {season: str(path) for season, path in sorted(sources.items())},
        "image_size": [WIDTH, HEIGHT],
        "class_names": list(output_class_names),
        "class_counts": dict(output_class_counts),
        "source_detailed_class_counts": dict(class_counts),
        "raw_switches": raw_switch_count,
        "total_switches": sum(output_class_counts.values()),
        "invalid_switch_counts": dict(invalid_counts),
        "collapsed_duplicate_boxes": collapsed_duplicate_boxes,
        "usable_images_by_season": dict(season_counts),
        "usable_images": sum(season_counts.values()),
        "positive_images": sum(positive_counts.values()),
        "negative_images": sum(split_counts.values()) - sum(positive_counts.values()),
        "box_size_px": {
            "width_p10": round(_percentile(box_widths, 0.10), 2),
            "width_median": round(statistics.median(box_widths), 2) if box_widths else 0,
            "height_p10": round(_percentile(box_heights, 0.10), 2),
            "height_median": round(statistics.median(box_heights), 2) if box_heights else 0,
        },
        "split_seed": seed,
        "temporal_block_size": block_size,
        "splits": {
            split: {
                "images": split_counts[split],
                "positive_images": positive_counts[split],
                "class_counts": dict(split_class_counts[split]),
                "blocks": len(split_blocks[split]),
            }
            for split in ("train", "val", "test")
        },
        "materialization_mode": materialize_mode,
        "stale_generated_files_removed": removed,
        "source_data_modified": False,
    }
    (output / "audit_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# L4R_NLB multi-season railway-switch dataset",
        "",
        f"YOLO类别模式：`{class_mode}`；类别：`{', '.join(output_class_names)}`。无道岔但有完整 JSON 的图片保留为空标签负样本。",
        "相邻帧按“季节 + frame_id 时间块”整体划分，避免连续画面跨 split。",
        "",
        f"- 可用图片：{report['usable_images']}（正样本 {report['positive_images']}，负样本 {report['negative_images']}）",
        f"- 道岔框：{report['total_switches']}，类别分布：`{json.dumps(report['class_counts'], ensure_ascii=False)}`",
        f"- 框尺寸：`{json.dumps(report['box_size_px'], ensure_ascii=False)}`",
        "",
        "| split | 图片 | 正样本 | 时间块 |",
        "|---|---:|---:|---:|",
    ]
    for split in ("train", "val", "test"):
        item = report["splits"][split]
        lines.append(f"| {split} | {item['images']} | {item['positive_images']} | {item['blocks']} |")
    lines.append("")
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", action="append", required=True, metavar="SEASON=PATH",
        help="Repeat for every season; PATH contains or directly wraps images/annotations",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=repo_root / "output/training-images/l4r_nlb_switches_yolo",
    )
    parser.add_argument("--block-size", type=int, default=250)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument(
        "--class-mode", choices=("detailed", "kind", "single"), default="detailed"
    )
    parser.add_argument("--materialize-mode", choices=("hardlink", "copy"), default="hardlink")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.block_size < 1:
        print("error: --block-size must be positive", file=sys.stderr)
        return 2
    try:
        report = prepare(
            _parse_sources(args.source), args.output_dir.resolve(), args.block_size,
            args.seed, args.materialize_mode, args.class_mode,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Prepared {report['usable_images']} images and {report['total_switches']} switch boxes")
    print(f"Output: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
