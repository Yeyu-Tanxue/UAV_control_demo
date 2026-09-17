import unittest

import numpy as np

from uav_demo.vision_control import (
    RailEstimate,
    RailMaskGeometry,
    VisionControlConfig,
    map_estimate_to_command,
)


def trapezoid_mask(
    *,
    near_center: float = 0.5,
    far_center: float = 0.5,
) -> np.ndarray:
    height, width = 480, 640
    mask = np.zeros((height, width), dtype=np.uint8)
    top = int(height * 0.50)
    bottom = int(height * 0.88)
    for y in range(top, bottom + 1):
        progress = (y - top) / (bottom - top)
        centre = far_center + progress * (near_center - far_center)
        half_width = 0.07 + progress * 0.24
        left = int(width * (centre - half_width))
        right = int(width * (centre + half_width))
        mask[y, left:right] = 1
    return mask


class RailMaskGeometryTests(unittest.TestCase):
    def test_centered_trapezoid_has_near_zero_errors(self) -> None:
        estimate = RailMaskGeometry().estimate(
            trapezoid_mask(),
            confidence=0.8,
        )

        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertAlmostEqual(estimate.lateral_error_norm, 0.0, delta=0.02)
        self.assertAlmostEqual(estimate.heading_error_deg, 0.0, delta=1.0)

    def test_top_edge_artifacts_do_not_move_the_control_line(self) -> None:
        mask = trapezoid_mask()
        mask[80:220, :180] = 1
        mask[80:220, 560:] = 1

        estimate = RailMaskGeometry().estimate(mask, confidence=0.8)

        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertAlmostEqual(estimate.lateral_error_norm, 0.0, delta=0.02)
        self.assertAlmostEqual(estimate.heading_error_deg, 0.0, delta=1.0)

    def test_right_bending_track_produces_positive_heading(self) -> None:
        estimate = RailMaskGeometry().estimate(
            trapezoid_mask(near_center=0.50, far_center=0.58),
            confidence=0.8,
        )

        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertGreater(estimate.heading_error_deg, 5.0)


class VisionControlMappingTests(unittest.TestCase):
    def test_aligned_track_moves_forward(self) -> None:
        estimate = RailEstimate(
            confidence=0.8,
            lateral_error_norm=0.0,
            heading_error_deg=0.0,
            valid_rows=20,
            near_center_x_norm=0.5,
            far_center_x_norm=0.5,
            near_width_norm=0.4,
            geometry_quality=1.0,
        )

        command = map_estimate_to_command(
            estimate,
            VisionControlConfig(forward_speed_m_s=0.12),
        )

        self.assertAlmostEqual(command.forward_m_s, 0.12)
        self.assertAlmostEqual(command.right_m_s, 0.0)
        self.assertAlmostEqual(command.yaw_rate_deg_s, 0.0)

    def test_large_heading_error_stops_forward_motion(self) -> None:
        estimate = RailEstimate(
            confidence=0.8,
            lateral_error_norm=0.2,
            heading_error_deg=25.0,
            valid_rows=20,
            near_center_x_norm=0.6,
            far_center_x_norm=0.8,
            near_width_norm=0.4,
            geometry_quality=1.0,
        )

        command = map_estimate_to_command(
            estimate,
            VisionControlConfig(),
        )

        self.assertEqual(command.forward_m_s, 0.0)
        self.assertGreater(command.right_m_s, 0.0)
        self.assertGreater(command.yaw_rate_deg_s, 0.0)


if __name__ == "__main__":
    unittest.main()
