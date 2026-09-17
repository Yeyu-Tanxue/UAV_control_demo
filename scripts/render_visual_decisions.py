#!/usr/bin/env python3
"""Render saved local-vision decisions over their original camera frames."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from uav_demo.vision_control import (
    RailEstimate,
    RailMaskGeometry,
    VisionControlConfig,
    map_estimate_to_command,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--last", type=int, default=3)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--confidence", type=float, default=0.15)
    parser.add_argument("--forward-speed", type=float, default=0.12)
    return parser


def _put_text(image, text: str, y: int) -> None:
    cv2.putText(
        image,
        text,
        (16, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        (16, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (20, 20, 20),
        1,
        cv2.LINE_AA,
    )


def _record_estimate(record: dict) -> RailEstimate:
    result = record["result"]
    near_x = 0.5 + 0.5 * float(result["lateral_error_norm"])
    return RailEstimate(
        confidence=float(result["confidence"]),
        lateral_error_norm=float(result["lateral_error_norm"]),
        heading_error_deg=float(result["heading_error_deg"]),
        valid_rows=int(result["valid_rows"]),
        near_center_x_norm=near_x,
        far_center_x_norm=0.5,
        near_width_norm=0.0,
        geometry_quality=1.0,
        source_id=str(result.get("source_id", "")),
    )


def main() -> None:
    args = _parser().parse_args()
    records = [
        json.loads(line)
        for line in args.decisions.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][-args.last :]
    output_dir = args.decisions.parent / "visualizations"
    output_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(args.model))
    geometry = RailMaskGeometry()
    summaries = []
    for record in records:
        cycle = int(record["cycle"])
        source = Path(record["result"]["source_id"])
        image = cv2.imread(str(source))
        if image is None:
            raise RuntimeError(f"Cannot read source frame: {source}")

        prediction = model.predict(
            source=image,
            imgsz=args.imgsz,
            conf=args.confidence,
            device="cpu",
            max_det=3,
            verbose=False,
        )[0]
        candidates = []
        if prediction.masks is not None and prediction.boxes is not None:
            for index in range(
                min(len(prediction.masks.data), len(prediction.boxes))
            ):
                mask = prediction.masks.data[index].cpu().numpy()
                estimate = geometry.estimate(
                    mask,
                    float(prediction.boxes.conf[index].item()),
                    str(source),
                )
                if estimate is not None:
                    candidates.append((estimate, mask))
        if not candidates:
            raise RuntimeError(f"No valid rail mask for cycle {cycle}: {source}")

        frame_records = record.get("frames", [])
        frame_record = next(
            (
                item
                for item in frame_records
                if item.get("source_id") == str(source)
            ),
            frame_records[-1] if frame_records else record["result"],
        )
        target_lateral = float(frame_record["lateral_error_norm"])
        target_heading = float(frame_record["heading_error_deg"])
        estimate, mask = min(
            candidates,
            key=lambda item: abs(
                item[0].lateral_error_norm - target_lateral
            )
            + abs(item[0].heading_error_deg - target_heading) / 20.0,
        )

        height, width = image.shape[:2]
        binary = cv2.resize(
            (mask > 0.5).astype(np.uint8),
            (width, height),
            interpolation=cv2.INTER_NEAREST,
        )
        overlay = image.copy()
        green = np.zeros_like(image)
        green[:, :] = (40, 210, 60)
        overlay[binary > 0] = cv2.addWeighted(
            image[binary > 0], 0.45, green[binary > 0], 0.55, 0
        )

        near_x = int(float(frame_record["near_center_x_norm"]) * width)
        far_x = int(float(frame_record["far_center_x_norm"]) * width)
        near_y = int(0.84 * height)
        far_y = int(0.58 * height)
        cv2.line(overlay, (far_x, far_y), (near_x, near_y), (0, 0, 255), 3)
        cv2.circle(overlay, (far_x, far_y), 6, (255, 180, 0), -1)
        cv2.circle(overlay, (near_x, near_y), 6, (0, 255, 255), -1)
        cv2.line(
            overlay,
            (width // 2, int(0.50 * height)),
            (width // 2, int(0.88 * height)),
            (255, 255, 255),
            1,
        )

        result_estimate = _record_estimate(record)
        command = map_estimate_to_command(
            result_estimate,
            VisionControlConfig(forward_speed_m_s=args.forward_speed),
        )
        _put_text(
            overlay,
            f"cycle {cycle}  conf={result_estimate.confidence:.3f}  "
            f"valid_rows={result_estimate.valid_rows}",
            26,
        )
        _put_text(
            overlay,
            f"lateral={result_estimate.lateral_error_norm:+.3f}  "
            f"heading={result_estimate.heading_error_deg:+.2f} deg",
            50,
        )
        _put_text(
            overlay,
            f"cmd forward={command.forward_m_s:.3f} m/s  "
            f"right={command.right_m_s:+.3f} m/s  "
            f"yaw={command.yaw_rate_deg_s:+.2f} deg/s",
            74,
        )

        stem = f"cycle_{cycle:02d}"
        cv2.imwrite(str(output_dir / f"{stem}_raw.png"), image)
        cv2.imwrite(str(output_dir / f"{stem}_mask.png"), binary * 255)
        cv2.imwrite(str(output_dir / f"{stem}_visualization.jpg"), overlay)
        summaries.append(
            {
                "cycle": cycle,
                "source": str(source),
                "recognition": record["result"],
                "command": {
                    "forward_m_s": command.forward_m_s,
                    "right_m_s": command.right_m_s,
                    "yaw_rate_deg_s": command.yaw_rate_deg_s,
                },
            }
        )

    (output_dir / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output_dir)


if __name__ == "__main__":
    main()
