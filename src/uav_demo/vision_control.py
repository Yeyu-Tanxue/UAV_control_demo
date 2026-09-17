"""Rail-mask geometry and conservative image-to-body control mapping."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RailEstimate:
    confidence: float
    lateral_error_norm: float
    heading_error_deg: float
    valid_rows: int
    near_center_x_norm: float
    far_center_x_norm: float
    near_width_norm: float
    geometry_quality: float
    source_id: str = ""


@dataclass(frozen=True, slots=True)
class BodyVelocityCommand:
    forward_m_s: float
    right_m_s: float
    yaw_rate_deg_s: float


@dataclass(frozen=True, slots=True)
class VisionControlConfig:
    forward_speed_m_s: float = 0.12
    lateral_gain_m_s: float = 0.16
    heading_gain: float = 0.35
    lateral_yaw_gain_deg_s: float = 3.0
    max_right_speed_m_s: float = 0.10
    max_yaw_rate_deg_s: float = 8.0
    full_stop_lateral_error_norm: float = 0.50
    full_stop_heading_error_deg: float = 20.0

    def __post_init__(self) -> None:
        if not 0.05 <= self.forward_speed_m_s <= 0.30:
            raise ValueError("forward_speed_m_s must be between 0.05 and 0.30")
        if self.lateral_gain_m_s <= 0:
            raise ValueError("lateral_gain_m_s must be positive")
        if self.heading_gain <= 0:
            raise ValueError("heading_gain must be positive")
        if self.max_right_speed_m_s <= 0:
            raise ValueError("max_right_speed_m_s must be positive")
        if self.max_yaw_rate_deg_s <= 0:
            raise ValueError("max_yaw_rate_deg_s must be positive")


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def map_estimate_to_command(
    estimate: RailEstimate,
    config: VisionControlConfig,
) -> BodyVelocityCommand:
    """Map image errors to a bounded PX4 body-frame velocity pulse."""

    lateral_severity = (
        abs(estimate.lateral_error_norm)
        / config.full_stop_lateral_error_norm
    )
    heading_severity = (
        abs(estimate.heading_error_deg)
        / config.full_stop_heading_error_deg
    )
    severity = max(lateral_severity, heading_severity)
    forward_scale = _clamp(1.0 - severity, 0.0, 1.0)

    right_m_s = _clamp(
        config.lateral_gain_m_s * estimate.lateral_error_norm,
        -config.max_right_speed_m_s,
        config.max_right_speed_m_s,
    )
    yaw_rate_deg_s = _clamp(
        config.heading_gain * estimate.heading_error_deg
        + config.lateral_yaw_gain_deg_s * estimate.lateral_error_norm,
        -config.max_yaw_rate_deg_s,
        config.max_yaw_rate_deg_s,
    )
    return BodyVelocityCommand(
        forward_m_s=config.forward_speed_m_s * forward_scale,
        right_m_s=right_m_s,
        yaw_rate_deg_s=yaw_rate_deg_s,
    )


class RailMaskGeometry:
    """Extract a track centreline from a segmentation mask, not its box.

    The estimator keeps the component supported by the central/lower ROI,
    walks scanlines from near to far, and chooses the segment continuous with
    the previous row. This rejects the top-corner and side blobs seen in the
    current Spring model output.
    """

    def __init__(
        self,
        roi_top: float = 0.50,
        roi_bottom: float = 0.88,
        sample_rows: int = 28,
        min_valid_rows: int = 12,
    ) -> None:
        if not 0.0 <= roi_top < roi_bottom <= 1.0:
            raise ValueError("ROI bounds must satisfy 0 <= top < bottom <= 1")
        self._roi_top = roi_top
        self._roi_bottom = roi_bottom
        self._sample_rows = sample_rows
        self._min_valid_rows = min_valid_rows

    @staticmethod
    def _runs(xs):
        import numpy as np

        if xs.size == 0:
            return []
        cuts = np.flatnonzero(np.diff(xs) > 1) + 1
        return [part for part in np.split(xs, cuts) if part.size >= 3]

    def estimate(
        self,
        mask,
        confidence: float,
        source_id: str = "",
    ) -> RailEstimate | None:
        import numpy as np

        binary = np.asarray(mask) > 0.5
        if binary.ndim != 2 or not binary.any():
            return None
        height, width = binary.shape
        top = int(round(height * self._roi_top))
        bottom = int(round(height * self._roi_bottom))
        rows = np.linspace(bottom, top, self._sample_rows, dtype=int)

        points: list[tuple[float, float, float]] = []
        previous_width_norm: float | None = None
        for y in rows:
            runs = [
                run
                for run in self._runs(np.flatnonzero(binary[y]))
                if 0.08 * width
                <= (float(run[0]) + float(run[-1])) * 0.5
                <= 0.92 * width
            ]
            if not runs:
                continue
            # The Spring mask is not always a filled polygon: sleepers can
            # split it into left/right rail fragments. The track centre is the
            # midpoint of the local mask envelope, not the midpoint of one
            # connected fragment and never the midpoint of the YOLO box.
            left = min(float(run[0]) for run in runs)
            right = max(float(run[-1]) for run in runs)
            width_norm = (right - left + 1.0) / width
            if not 0.04 <= width_norm <= 0.90:
                continue
            # In a forward-looking pinhole view, a single straight track gets
            # narrower toward the horizon. A sudden far-field widening is the
            # characteristic top/side blob produced by this Spring model.
            if (
                previous_width_norm is not None
                and width_norm > previous_width_norm + 0.04
            ):
                continue
            centre = (left + right) * 0.5
            points.append(
                (y / height, centre / width, width_norm)
            )
            previous_width_norm = width_norm

        if len(points) < self._min_valid_rows:
            return None

        ys = np.asarray([point[0] for point in points], dtype=float)
        xs = np.asarray([point[1] for point in points], dtype=float)
        widths = np.asarray([point[2] for point in points], dtype=float)

        keep = np.ones(xs.shape, dtype=bool)
        for _ in range(2):
            slope, intercept = np.polyfit(ys[keep], xs[keep], 1)
            residual = np.abs(xs - (slope * ys + intercept))
            residual_median = float(np.median(residual[keep]))
            mad = float(
                np.median(np.abs(residual[keep] - residual_median))
            )
            threshold = max(
                0.025,
                residual_median + 3.0 * max(mad, 1e-6),
            )
            candidate = residual <= threshold
            if int(candidate.sum()) < self._min_valid_rows:
                break
            keep = candidate

        slope, intercept = np.polyfit(ys[keep], xs[keep], 1)
        near_y = float(np.quantile(ys[keep], 0.85))
        far_y = float(np.quantile(ys[keep], 0.20))
        near_x = float(slope * near_y + intercept)
        far_x = float(slope * far_y + intercept)
        lateral_error = (near_x - 0.5) / 0.5
        delta_x_px = (far_x - near_x) * width
        delta_y_px = (near_y - far_y) * height
        heading_error = math.degrees(math.atan2(delta_x_px, delta_y_px))
        near_width = float(
            np.median(widths[ys >= np.quantile(ys, 0.65)])
        )
        median_residual = float(
            np.median(
                np.abs(xs[keep] - (slope * ys[keep] + intercept))
            )
        )
        row_support = float(keep.sum()) / float(self._sample_rows)
        geometry_quality = row_support * _clamp(
            1.0 - median_residual / 0.08,
            0.0,
            1.0,
        )

        if not 0.03 <= near_width <= 0.95:
            return None
        if not -1.2 <= lateral_error <= 1.2:
            return None
        return RailEstimate(
            confidence=float(confidence),
            lateral_error_norm=float(lateral_error),
            heading_error_deg=float(heading_error),
            valid_rows=int(keep.sum()),
            near_center_x_norm=near_x,
            far_center_x_norm=far_x,
            near_width_norm=near_width,
            geometry_quality=geometry_quality,
            source_id=source_id,
        )
