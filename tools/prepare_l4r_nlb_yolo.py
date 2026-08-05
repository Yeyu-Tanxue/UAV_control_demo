#!/usr/bin/env python3
"""Convert L4R_NLB ego-track JSON annotations to YOLO segmentation format."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

try:
    from tools.prepare_railgoerl24 import assign_sequence_splits
except ModuleNotFoundError:  # Direct execution from tools/.
    from prepare_railgoerl24 import assign_sequence_splits


FRAME_RE = re.compile(r"(\d+)$")
SPLIT_RATIOS = {"train": 0.80, "val": 0.10, "test": 0.10}


def frame_number(stem: str) -> int:
    match = FRAME_RE.search(stem)
    if not match:
        raise ValueError(f"Cannot parse frame number from: {stem}")
    return int(match.group(1))


def polygon_area(points: Sequence[tuple[float, float]]) -> float:
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
        / 2.0
    )


def _orientation(
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
) -> float:
    return (second[0] - first[0]) * (third[1] - first[1]) - (
        second[1] - first[1]
    ) * (third[0] - first[0])


def has_proper_self_intersection(points: Sequence[tuple[float, float]]) -> bool:
    """Detect non-adjacent segment crossings; touching endpoints are allowed."""

    count = len(points)
    for first_index in range(count):
        first_a = points[first_index]
        first_b = points[(first_index + 1) % count]
        for second_index in range(first_index + 1, count):
            if second_index in {first_index, (first_index + 1) % count}:
                continue
            if first_index == 0 and second_index == count - 1:
                continue
            second_a = points[second_index]
            second_b = points[(second_index + 1) % count]
            first_side = _orientation(first_a, first_b, second_a) * _orientation(
                first_a, first_b, second_b
            )
            second_side = _orientation(second_a, second_b, first_a) * _orientation(
                second_a, second_b, first_b
            )
            if first_side < 0 and second_side < 0:
                return True
    return False


def ego_polygon(
    annotation: dict[str, object], width: int, height: int
) -> tuple[list[tuple[float, float]] | None, str, int]:
    tracks = annotation.get("tracks", {})
    if not isinstance(tracks, dict):
        return None, "invalid_tracks", 0
    ego_tracks = [
        track
        for track in tracks.values()
        if isinstance(track, dict) and track.get("relative position") == "ego"
    ]
    if len(ego_tracks) != 1:
        return None, f"ego_track_count_{len(ego_tracks)}", len(ego_tracks)

    ego = ego_tracks[0]
    left = ego.get("left rail", {})
    right = ego.get("right rail", {})
    left_points = left.get("points", []) if isinstance(left, dict) else []
    right_points = right.get("points", []) if isinstance(right, dict) else []
    if not isinstance(left_points, list) or not isinstance(right_points, list):
        return None, "invalid_point_lists", 1
    if len(left_points) < 2 or len(right_points) < 2:
        return None, "insufficient_rail_points", 1

    raw_points = left_points + list(reversed(right_points))
    clipped: list[tuple[float, float]] = []
    for point in raw_points:
        if not isinstance(point, dict) or "x" not in point or "y" not in point:
            return None, "invalid_point", 1
        try:
            x = max(0.0, min(float(width - 1), float(point["x"])))
            y = max(0.0, min(float(height - 1), float(point["y"])))
        except (TypeError, ValueError):
            return None, "invalid_point", 1
        current = (x, y)
        if not clipped or current != clipped[-1]:
            clipped.append(current)
    if len(clipped) > 1 and clipped[0] == clipped[-1]:
        clipped.pop()
    if len(set(clipped)) < 3:
        return None, "degenerate_polygon", 1
    if has_proper_self_intersection(clipped):
        return None, "self_intersecting_polygon", 1
    if polygon_area(clipped) < 100.0:
        return None, "tiny_polygon", 1
    return clipped, "usable", 1


def yolo_line(points: Sequence[tuple[float, float]], width: int, height: int) -> str:
    coordinates = " ".join(
        f"{x / width:.6f} {y / height:.6f}" for x, y in points
    )
    return f"0 {coordinates}\n"


def _relative(path: Path, root: Path) -> str:
    return PurePosixPath(path.relative_to(root)).as_posix()


def audit_source(
    source_root: Path,
    width: int = 1920,
    height: int = 1080,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    source_root = source_root.resolve()
    image_dir = source_root / "images"
    annotation_dir = source_root / "annotations"
    mask_dir = source_root / "masks"
    if not all(path.is_dir() for path in (image_dir, annotation_dir, mask_dir)):
        raise FileNotFoundError(
            f"Expected images/, annotations/ and masks/ below {source_root}"
        )

    images = {path.stem: path for path in image_dir.glob("*.png")}
    annotations = {path.stem: path for path in annotation_dir.glob("*.json")}
    masks = {path.stem: path for path in mask_dir.glob("*.png")}
    rows: list[dict[str, object]] = []
    reasons: Counter[str] = Counter()
    positions: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    total_tracks = 0
    total_switches = 0

    for stem in sorted(annotations, key=frame_number):
        annotation_path = annotations[stem]
        image_path = images.get(stem)
        mask_path = masks.get(stem)
        row: dict[str, object] = {
            "stem": stem,
            "frame_id": frame_number(stem),
            "source_image_path": _relative(image_path, source_root) if image_path else "",
            "source_annotation_path": _relative(annotation_path, source_root),
            "source_mask_path": _relative(mask_path, source_root) if mask_path else "",
            "source_mask_scope": "all_tracks",
        }
        try:
            data = json.loads(annotation_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            row.update(status="excluded", exclude_reason="json_parse_error", error=str(exc))
            reasons["json_parse_error"] += 1
            rows.append(row)
            continue

        tracks = data.get("tracks", {})
        if isinstance(tracks, dict):
            total_tracks += len(tracks)
            for track in tracks.values():
                if isinstance(track, dict):
                    positions[str(track.get("relative position", "missing"))] += 1
        switches = data.get("switches", {})
        switch_count = len(switches) if isinstance(switches, dict) else 0
        total_switches += switch_count
        tag_groups = data.get("tag groups", {})
        flat_tags: list[str] = []
        if isinstance(tag_groups, dict):
            for group, values in tag_groups.items():
                if isinstance(values, list):
                    for value in values:
                        label = f"{group}:{value}"
                        flat_tags.append(label)
                        tags[label] += 1

        polygon, reason, ego_count = ego_polygon(data, width, height)
        if image_path is None:
            reason = "missing_image"
            polygon = None
        elif mask_path is None:
            reason = "missing_mask"
            polygon = None
        row.update(
            status="usable" if polygon is not None else "excluded",
            exclude_reason="" if polygon is not None else reason,
            ego_track_count=ego_count,
            total_track_count=len(tracks) if isinstance(tracks, dict) else 0,
            switch_count=switch_count,
            tags=json.dumps(sorted(flat_tags), ensure_ascii=False),
            polygon_points=len(polygon) if polygon else 0,
            polygon_area_px=round(polygon_area(polygon), 2) if polygon else 0,
            polygon=polygon,
        )
        reasons[reason] += 1
        rows.append(row)

    image_only = sorted(set(images) - set(annotations), key=frame_number)
    annotation_only = sorted(set(annotations) - set(images), key=frame_number)
    mask_only = sorted(set(masks) - set(annotations), key=frame_number)
    report: dict[str, object] = {
        "dataset": "L4R_NLB_winter",
        "image_count": len(images),
        "annotation_count": len(annotations),
        "mask_count": len(masks),
        "usable_count": reasons["usable"],
        "excluded_count": len(rows) - reasons["usable"],
        "exclusion_reasons": {
            reason: count for reason, count in sorted(reasons.items()) if reason != "usable"
        },
        "image_without_annotation_count": len(image_only),
        "image_without_annotation": image_only,
        "annotation_without_image_count": len(annotation_only),
        "mask_without_annotation_count": len(mask_only),
        "total_track_count": total_tracks,
        "track_position_counts": dict(sorted(positions.items())),
        "switch_count": total_switches,
        "tag_counts": dict(tags.most_common()),
        "source_masks_used_as_labels": False,
        "label_definition": "ego_track_area from ego left/right rail points",
        "source_data_modified": False,
    }
    return rows, report


def assign_temporal_block_splits(
    rows: list[dict[str, object]], block_size: int, seed: int
) -> dict[int, str]:
    usable = [row for row in rows if row["status"] == "usable"]
    block_counts: Counter[int] = Counter(
        int(row["frame_id"]) // block_size for row in usable
    )
    assignments = assign_sequence_splits(
        {f"block_{block:04d}": count for block, count in block_counts.items()},
        ratios=SPLIT_RATIOS,
        seed=seed,
    )
    return {
        block: assignments[f"block_{block:04d}"] for block in block_counts
    }


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
    if mode == "copy":
        shutil.copy2(source, destination)
        return
    raise ValueError(f"Unsupported materialization mode: {mode}")


def _write_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    rows = list(rows)
    fields = [
        "stem",
        "frame_id",
        "temporal_block",
        "split",
        "status",
        "exclude_reason",
        "source_image_path",
        "source_annotation_path",
        "source_mask_path",
        "source_mask_scope",
        "yolo_image_path",
        "yolo_label_path",
        "ego_track_count",
        "total_track_count",
        "switch_count",
        "polygon_points",
        "polygon_area_px",
        "tags",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_report(path: Path, report: dict[str, object]) -> None:
    splits = report["splits"]
    lines = [
        "# L4R_NLB winter → YOLO分割转换报告",
        "",
        "- 类别：`ego_track_area`；",
        "- 标签来源：JSON中 `relative position = ego` 的左右钢轨点；",
        "- 官方mask包含所有轨道，未直接作为YOLO标签；",
        f"- 图片 / JSON / mask：{report['image_count']} / {report['annotation_count']} / {report['mask_count']}；",
        f"- 可用 / 排除：{report['usable_count']} / {report['excluded_count']}；",
        f"- 排除原因：`{json.dumps(report['exclusion_reasons'], ensure_ascii=False, sort_keys=True)}`；",
        f"- 无JSON图片：{report['image_without_annotation_count']}；",
        f"- 轨道 / 道岔标注：{report['total_track_count']} / {report['switch_count']}。",
        "",
        "## 连续帧块划分",
        "",
        "| split | 图片数 | 时间块数 |",
        "|---|---:|---:|",
    ]
    for split in ("train", "val", "test"):
        lines.append(f"| {split} | {splits[split]['images']} | {splits[split]['blocks']} |")
    lines.extend(
        [
            "",
            "相邻frame_id先归入同一时间块，再按完整块划分，避免相近画面跨split。",
            "RailGoerl24仍是最终域内验证来源；本数据主要用于轨道分割预训练。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _remove_stale_generated_files(
    output_dir: Path, expected: dict[str, set[str]]
) -> int:
    """Remove only obsolete converter outputs from explicit split folders."""

    removed = 0
    for category, suffix in (("images", ".png"), ("labels", ".txt")):
        for split in ("train", "val", "test"):
            split_dir = output_dir / category / split
            if not split_dir.is_dir():
                continue
            for path in split_dir.glob(f"*{suffix}"):
                if path.stem not in expected[split]:
                    path.unlink()
                    removed += 1
    return removed


def prepare(
    source_root: Path,
    output_dir: Path,
    block_size: int = 250,
    seed: int = 20260805,
    materialize_mode: str = "hardlink",
) -> dict[str, object]:
    rows, report = audit_source(source_root)
    assignments = assign_temporal_block_splits(rows, block_size, seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    split_blocks: dict[str, set[int]] = defaultdict(set)
    split_counts: Counter[str] = Counter()
    expected_stems: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        row.pop("polygon", None) if row["status"] != "usable" else None
        if row["status"] != "usable":
            row.update(temporal_block="", split="", yolo_image_path="", yolo_label_path="")
            continue
        block = int(row["frame_id"]) // block_size
        split = assignments[block]
        image_relative = Path("images") / split / f"{row['stem']}.png"
        label_relative = Path("labels") / split / f"{row['stem']}.txt"
        polygon = row.pop("polygon")
        source_image = source_root / str(row["source_image_path"])
        _materialize(source_image, output_dir / image_relative, materialize_mode)
        (output_dir / label_relative).parent.mkdir(parents=True, exist_ok=True)
        (output_dir / label_relative).write_text(
            yolo_line(polygon, 1920, 1080), encoding="utf-8"
        )
        row.update(
            temporal_block=block,
            split=split,
            yolo_image_path=PurePosixPath(image_relative).as_posix(),
            yolo_label_path=PurePosixPath(label_relative).as_posix(),
        )
        split_counts[split] += 1
        split_blocks[split].add(block)
        expected_stems[split].add(str(row["stem"]))

    stale_files_removed = _remove_stale_generated_files(output_dir, expected_stems)

    _write_csv(output_dir / "manifest.csv", rows)
    dataset_yaml = "\n".join(
        [
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "names:",
            "  0: ego_track_area",
            "",
        ]
    )
    (output_dir / "dataset.yaml").write_text(dataset_yaml, encoding="utf-8")
    report.update(
        split_seed=seed,
        temporal_block_size=block_size,
        split_target_ratios=SPLIT_RATIOS,
        splits={
            split: {"images": split_counts[split], "blocks": len(split_blocks[split])}
            for split in ("train", "val", "test")
        },
        materialization_mode=materialize_mode,
        stale_generated_files_removed=stale_files_removed,
    )
    (output_dir / "audit_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_report(output_dir / "README.md", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Inner L4R_NLB_winter directory containing images/annotations/masks",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "output" / "training-images" / "l4r_nlb_winter_yolo",
    )
    parser.add_argument("--block-size", type=int, default=250)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--materialize-mode", choices=("hardlink", "copy"), default="hardlink")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.block_size < 1:
        print("error: --block-size must be positive", file=sys.stderr)
        return 2
    try:
        report = prepare(
            args.source_root,
            args.output_dir,
            args.block_size,
            args.seed,
            args.materialize_mode,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"Prepared {report['usable_count']} ego-track samples; "
        f"excluded {report['excluded_count']}."
    )
    print(f"Output: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
