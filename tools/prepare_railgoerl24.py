#!/usr/bin/env python3
"""Audit RailGoerl24 and prepare leakage-safe manifests for rail annotation.

The tool is intentionally read-only with respect to the source dataset.  It
matches images to the manually reviewed XML tree, assigns complete video
sequences to train/validation/test splits, and selects evenly spaced frames
for the additional left/right rail annotation required by the UAV demo.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


DEFAULT_SPLIT_RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}
FRAME_NUMBER_RE = re.compile(r"(\d+)$")


@dataclass(frozen=True)
class ParsedAnnotation:
    width: int | None
    height: int | None
    everything_annotated: str
    object_count: int
    class_assignment_count: int
    label_counts: dict[str, int]
    invalid_box_count: int
    objects_without_label: int


def _text(element: ET.Element | None, default: str = "") -> str:
    return default if element is None or element.text is None else element.text.strip()


def _integer(element: ET.Element | None) -> int | None:
    value = _text(element)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_annotation(xml_path: Path) -> ParsedAnnotation:
    """Parse the dataset's Pascal-VOC-like XML without changing its semantics."""

    root = ET.parse(xml_path).getroot()
    width = _integer(root.find("./size/width"))
    height = _integer(root.find("./size/height"))
    label_counts: Counter[str] = Counter()
    invalid_box_count = 0
    objects_without_label = 0
    objects = root.findall("./object")

    for obj in objects:
        # RailGoerl24 uses object/classes/name.  The fallback accepts ordinary
        # Pascal VOC so the audit also catches unexpected exporter variants.
        labels = [_text(node) for node in obj.findall("./classes/name")]
        if not labels:
            labels = [_text(node) for node in obj.findall("./name")]
        labels = [label for label in labels if label]
        if not labels:
            objects_without_label += 1
        label_counts.update(labels)

        box = obj.find("./bndbox")
        coords = {
            name: _integer(box.find(name)) if box is not None else None
            for name in ("xmin", "ymin", "xmax", "ymax")
        }
        valid = all(value is not None for value in coords.values())
        if valid:
            xmin, ymin = coords["xmin"], coords["ymin"]
            xmax, ymax = coords["xmax"], coords["ymax"]
            valid = bool(
                xmin is not None
                and ymin is not None
                and xmax is not None
                and ymax is not None
                and xmin < xmax
                and ymin < ymax
                and xmin >= 0
                and ymin >= 0
                and (width is None or xmax <= width)
                and (height is None or ymax <= height)
            )
        if not valid:
            invalid_box_count += 1

    return ParsedAnnotation(
        width=width,
        height=height,
        everything_annotated=_text(root.find("./everythingAnnotated")),
        object_count=len(objects),
        class_assignment_count=sum(label_counts.values()),
        label_counts=dict(sorted(label_counts.items())),
        invalid_box_count=invalid_box_count,
        objects_without_label=objects_without_label,
    )


def _relative_posix(path: Path, root: Path) -> str:
    return PurePosixPath(path.relative_to(root)).as_posix()


def _frame_number(image_path: Path) -> int | None:
    match = FRAME_NUMBER_RE.search(image_path.stem)
    return int(match.group(1)) if match else None


def _stable_tie_breaker(name: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{name}".encode("utf-8")).hexdigest()


def assign_sequence_splits(
    sequence_sizes: dict[str, int],
    ratios: dict[str, float] | None = None,
    seed: int = 20260804,
) -> dict[str, str]:
    """Greedily balance frame totals while keeping each sequence intact."""

    ratios = ratios or DEFAULT_SPLIT_RATIOS
    if not sequence_sizes:
        return {}
    if any(size <= 0 for size in sequence_sizes.values()):
        raise ValueError("Every sequence must contain at least one frame")
    if not math.isclose(sum(ratios.values()), 1.0, abs_tol=1e-9):
        raise ValueError("Split ratios must sum to 1")

    split_names = list(ratios)
    total = sum(sequence_sizes.values())
    targets = {name: total * ratios[name] for name in split_names}
    assigned = {name: 0 for name in split_names}
    result: dict[str, str] = {}

    ordered = sorted(
        sequence_sizes,
        key=lambda name: (-sequence_sizes[name], _stable_tie_breaker(name, seed)),
    )
    for sequence in ordered:
        size = sequence_sizes[sequence]

        def score(split: str) -> tuple[float, float, int]:
            simulated = dict(assigned)
            simulated[split] += size
            normalized_error = sum(
                abs(simulated[name] - targets[name]) / max(targets[name], 1.0)
                for name in split_names
            )
            remaining_fraction = (targets[split] - assigned[split]) / max(
                targets[split], 1.0
            )
            return (normalized_error, -remaining_fraction, split_names.index(split))

        chosen = min(split_names, key=score)
        assigned[chosen] += size
        result[sequence] = chosen

    return result


def evenly_spaced_rows(rows: Sequence[dict[str, object]], count: int) -> list[dict[str, object]]:
    """Select centered, evenly spaced samples without duplicating a frame."""

    if count <= 0 or not rows:
        return []
    count = min(count, len(rows))
    indices = [min(len(rows) - 1, int((index + 0.5) * len(rows) / count)) for index in range(count)]
    # The formula is unique for count <= len(rows); keeping this guard makes
    # the contract explicit if the sampling formula is changed later.
    unique_indices = list(dict.fromkeys(indices))
    return [rows[index] for index in unique_indices]


def _scenario_hint(sequence_id: str) -> str:
    lowered = sequence_id.lower()
    if "weichen" in lowered or "switch" in lowered:
        return "switch_review"
    if "gegenstaende" in lowered or "obstacle" in lowered:
        return "object_on_track"
    return "normal"


def scan_dataset(dataset_root: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Return one row per image plus pairing/annotation audit statistics."""

    dataset_root = dataset_root.resolve()
    image_root = dataset_root / "imgs"
    annotation_root = dataset_root / "annots"
    if not image_root.is_dir() or not annotation_root.is_dir():
        raise FileNotFoundError(
            f"Expected 'imgs' and 'annots' below dataset root: {dataset_root}"
        )

    images = sorted(image_root.rglob("*.jpg"))
    manual_xmls = {
        _relative_posix(path, annotation_root)
        for path in annotation_root.rglob("*.xml")
        if not any(part.endswith("_auto_annots") for part in path.parts)
    }
    rows: list[dict[str, object]] = []
    missing_xml: list[str] = []
    parse_errors: list[dict[str, str]] = []
    matched_xml: set[str] = set()
    label_totals: Counter[str] = Counter()
    totals: Counter[str] = Counter()

    for image_path in images:
        relative_image = image_path.relative_to(image_root)
        relative_xml = relative_image.with_suffix(".xml")
        xml_key = PurePosixPath(relative_xml).as_posix()
        xml_path = annotation_root / relative_xml
        sequence_id = PurePosixPath(relative_image.parent).as_posix()
        base_row: dict[str, object] = {
            "image_path": f"imgs/{PurePosixPath(relative_image).as_posix()}",
            "annotation_path": f"annots/{xml_key}",
            "sequence_id": sequence_id,
            "frame_id": _frame_number(image_path),
            "camera_height_m": "2.45",
        }
        if not xml_path.is_file():
            missing_xml.append(base_row["image_path"] if isinstance(base_row["image_path"], str) else str(base_row["image_path"]))
            base_row.update(
                object_count="",
                class_assignment_count="",
                person_count="",
                bicycle_count="",
                other_label_counts="",
                invalid_box_count="",
                objects_without_label="",
                image_width="",
                image_height="",
                everything_annotated="",
            )
            rows.append(base_row)
            continue

        matched_xml.add(xml_key)
        try:
            parsed = parse_annotation(xml_path)
        except (ET.ParseError, OSError, ValueError) as exc:
            parse_errors.append({"annotation_path": f"annots/{xml_key}", "error": str(exc)})
            base_row.update(
                object_count="",
                class_assignment_count="",
                person_count="",
                bicycle_count="",
                other_label_counts="",
                invalid_box_count="",
                objects_without_label="",
                image_width="",
                image_height="",
                everything_annotated="",
            )
            rows.append(base_row)
            continue

        other_labels = {
            label: count
            for label, count in parsed.label_counts.items()
            if label not in {"person", "bicycle"}
        }
        base_row.update(
            object_count=parsed.object_count,
            class_assignment_count=parsed.class_assignment_count,
            person_count=parsed.label_counts.get("person", 0),
            bicycle_count=parsed.label_counts.get("bicycle", 0),
            other_label_counts=json.dumps(other_labels, ensure_ascii=False, sort_keys=True),
            invalid_box_count=parsed.invalid_box_count,
            objects_without_label=parsed.objects_without_label,
            image_width=parsed.width if parsed.width is not None else "",
            image_height=parsed.height if parsed.height is not None else "",
            everything_annotated=parsed.everything_annotated,
        )
        rows.append(base_row)
        label_totals.update(parsed.label_counts)
        totals.update(
            object_count=parsed.object_count,
            class_assignment_count=parsed.class_assignment_count,
            invalid_box_count=parsed.invalid_box_count,
            objects_without_label=parsed.objects_without_label,
        )
        if parsed.object_count:
            totals["frames_with_objects"] += 1

    orphan_xml = sorted(manual_xmls - matched_xml)
    totals["empty_frames"] = sum(row.get("object_count") == 0 for row in rows)
    audit: dict[str, object] = {
        "dataset": "RailGoerl24 Annotated_RGB_data",
        "camera_height_m": 2.45,
        "image_count": len(images),
        "manual_xml_count": len(manual_xmls),
        "matched_pair_count": len(matched_xml),
        "sequence_count": len({row["sequence_id"] for row in rows}),
        "missing_xml_count": len(missing_xml),
        "missing_xml": missing_xml,
        "orphan_xml_count": len(orphan_xml),
        "orphan_xml": [f"annots/{path}" for path in orphan_xml],
        "parse_error_count": len(parse_errors),
        "parse_errors": parse_errors,
        "object_count": totals["object_count"],
        "class_assignment_count": totals["class_assignment_count"],
        "frames_with_objects": totals["frames_with_objects"],
        "empty_frames": totals["empty_frames"],
        "label_counts": dict(sorted(label_totals.items())),
        "invalid_box_count": totals["invalid_box_count"],
        "objects_without_label": totals["objects_without_label"],
        "source_data_modified": False,
        "auto_annotations_used": False,
    }
    return rows, audit


def _write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_report(path: Path, report: dict[str, object]) -> None:
    split_summary = report["splits"]
    lines = [
        "# RailGoerl24 数据准备报告",
        "",
        "> 本报告由 `tools/prepare_railgoerl24.py` 生成；源图片和 XML 均未修改。",
        "",
        "## 审计结果",
        "",
        f"- 图片：{report['image_count']:,}",
        f"- 人工 XML：{report['manual_xml_count']:,}",
        f"- 完整配对：{report['matched_pair_count']:,}",
        f"- 视频序列：{report['sequence_count']:,}",
        f"- 对象：{report['object_count']:,}",
        f"- 类别标记：{report['class_assignment_count']:,}",
        f"- 类别统计：`{json.dumps(report['label_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- 空帧：{report['empty_frames']:,}",
        f"- 无效框：{report['invalid_box_count']:,}",
        f"- 缺少 XML / 孤立 XML / 解析错误：{report['missing_xml_count']} / {report['orphan_xml_count']} / {report['parse_error_count']}",
        "- 自动标注目录：未使用",
        "",
        "## 按完整视频序列划分",
        "",
        "| split | 序列数 | 帧数 | 帧占比 |",
        "|---|---:|---:|---:|",
    ]
    for split in ("train", "val", "test"):
        item = split_summary[split]
        lines.append(
            f"| {split} | {item['sequences']} | {item['frames']} | {item['frame_ratio']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## 铁轨标注候选",
            "",
            f"共选出 **{report['rail_annotation_candidate_count']:,}** 帧；每个序列最多均匀抽取 {report['candidate_frames_per_sequence']} 帧。",
            "标注时添加 `left_rail`、`right_rail` 两条折线，轨道中心线由两条轨的同高度中点派生，不另做重复人工标注。",
            "`switch_review` 候选须人工判断：道岔或多股轨道不清晰时先标记为排除，不进入第一版训练。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def prepare(
    dataset_root: Path,
    output_dir: Path,
    candidate_frames_per_sequence: int = 8,
    seed: int = 20260804,
    strict: bool = False,
) -> dict[str, object]:
    rows, audit = scan_dataset(dataset_root)
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["sequence_id"])].append(row)
    for sequence_rows in grouped.values():
        sequence_rows.sort(
            key=lambda row: (
                row["frame_id"] is None,
                row["frame_id"] if row["frame_id"] is not None else 0,
                str(row["image_path"]),
            )
        )

    assignments = assign_sequence_splits(
        {sequence: len(sequence_rows) for sequence, sequence_rows in grouped.items()},
        seed=seed,
    )
    for row in rows:
        row["split"] = assignments[str(row["sequence_id"])]

    candidates: list[dict[str, object]] = []
    for sequence in sorted(grouped):
        for row in evenly_spaced_rows(grouped[sequence], candidate_frames_per_sequence):
            candidate = dict(row)
            candidate.update(
                scenario_hint=_scenario_hint(sequence),
                rail_annotation_status="pending",
                exclude_reason="",
                left_rail_points="",
                right_rail_points="",
            )
            candidates.append(candidate)

    manifest_fields = [
        "image_path",
        "annotation_path",
        "sequence_id",
        "frame_id",
        "camera_height_m",
        "split",
        "object_count",
        "class_assignment_count",
        "person_count",
        "bicycle_count",
        "other_label_counts",
        "invalid_box_count",
        "objects_without_label",
        "image_width",
        "image_height",
        "everything_annotated",
    ]
    candidate_fields = [
        "image_path",
        "annotation_path",
        "sequence_id",
        "frame_id",
        "split",
        "camera_height_m",
        "person_count",
        "bicycle_count",
        "scenario_hint",
        "rail_annotation_status",
        "exclude_reason",
        "left_rail_points",
        "right_rail_points",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "dataset_manifest.csv", rows, manifest_fields)
    _write_csv(output_dir / "rail_annotation_candidates.csv", candidates, candidate_fields)

    split_summary: dict[str, dict[str, float | int]] = {}
    for split in DEFAULT_SPLIT_RATIOS:
        sequences = {sequence for sequence, assigned in assignments.items() if assigned == split}
        frame_count = sum(len(grouped[sequence]) for sequence in sequences)
        split_summary[split] = {
            "sequences": len(sequences),
            "frames": frame_count,
            "frame_ratio": frame_count / len(rows) if rows else 0.0,
        }
    report = {
        **audit,
        "split_seed": seed,
        "split_target_ratios": DEFAULT_SPLIT_RATIOS,
        "splits": split_summary,
        "candidate_frames_per_sequence": candidate_frames_per_sequence,
        "rail_annotation_candidate_count": len(candidates),
        "output_files": [
            "dataset_manifest.csv",
            "rail_annotation_candidates.csv",
            "audit_report.json",
            "audit_report.md",
        ],
    }
    (output_dir / "audit_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_report(output_dir / "audit_report.md", report)

    problem_count = (
        int(report["missing_xml_count"])
        + int(report["orphan_xml_count"])
        + int(report["parse_error_count"])
        + int(report["invalid_box_count"])
        + int(report["objects_without_label"])
    )
    if strict and problem_count:
        raise RuntimeError(f"Strict audit failed with {problem_count} data problems")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        required=True,
        help="Extracted Annotated_RGB_data directory containing imgs/ and annots/",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "output" / "training-images" / "railgoerl24",
        help="Directory for manifests and reports",
    )
    parser.add_argument(
        "--candidate-frames-per-sequence",
        type=int,
        default=8,
        help="Maximum evenly spaced rail-annotation candidates per video sequence",
    )
    parser.add_argument("--seed", type=int, default=20260804, help="Deterministic split seed")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return an error if pairing, parsing, box, or label problems are found",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.candidate_frames_per_sequence < 1:
        print("--candidate-frames-per-sequence must be at least 1", file=sys.stderr)
        return 2
    try:
        report = prepare(
            dataset_root=args.dataset_root,
            output_dir=args.output_dir,
            candidate_frames_per_sequence=args.candidate_frames_per_sequence,
            seed=args.seed,
            strict=args.strict,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"Prepared {report['image_count']} frames from {report['sequence_count']} sequences; "
        f"selected {report['rail_annotation_candidate_count']} rail candidates."
    )
    print(f"Output: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
