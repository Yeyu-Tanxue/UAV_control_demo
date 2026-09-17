import math
import unittest
from pathlib import Path

from uav_demo.camera_geometry import load_gazebo_camera_geometry


REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "simulation" / "gazebo" / "models"
SENSOR_MODEL_PATH = MODELS_DIR / "mono_cam" / "model.sdf"
VEHICLE_MODEL_PATH = MODELS_DIR / "x500_mono_cam" / "model.sdf"


class CameraGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.geometry = load_gazebo_camera_geometry(
            SENSOR_MODEL_PATH,
            VEHICLE_MODEL_PATH,
        )

    def test_intrinsics_are_derived_from_sdf_horizontal_fov(self) -> None:
        intrinsics = self.geometry.intrinsics

        self.assertEqual((intrinsics.width_px, intrinsics.height_px), (640, 480))
        self.assertAlmostEqual(intrinsics.fx_px, 224.066412228004, places=9)
        self.assertAlmostEqual(intrinsics.fy_px, intrinsics.fx_px, places=12)
        self.assertEqual((intrinsics.cx_px, intrinsics.cy_px), (320.0, 240.0))
        self.assertAlmostEqual(
            math.degrees(intrinsics.horizontal_fov_rad),
            110.0,
            places=8,
        )
        self.assertAlmostEqual(
            math.degrees(intrinsics.vertical_fov_rad),
            93.9329234766631,
            places=8,
        )
        self.assertEqual(intrinsics.distortion, (0.0,) * 5)

    def test_fixed_mount_is_forward_up_and_pitched_down(self) -> None:
        mount = self.geometry.mount

        self.assertEqual(mount.parent_frame, "base_link")
        self.assertEqual(mount.child_frame, "camera_link")
        for actual, expected in zip(mount.translation_body_m, (0.12, 0.0, -0.06)):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(math.degrees(mount.roll_rad), 0.0)
        self.assertAlmostEqual(math.degrees(mount.pitch_rad), 35.0, places=8)
        self.assertAlmostEqual(math.degrees(mount.yaw_rad), 0.0)

        centre_ray = mount.optical_axis_body
        self.assertAlmostEqual(centre_ray[0], math.cos(math.radians(35.0)), places=9)
        self.assertAlmostEqual(centre_ray[1], 0.0, places=12)
        self.assertAlmostEqual(centre_ray[2], -math.sin(math.radians(35.0)), places=9)

    def test_opencv_axes_are_explicit_in_the_body_frame(self) -> None:
        mount = self.geometry.mount

        # Image-right is body-right, which is -Y in Gazebo FLU.
        right = mount.optical_right_body
        self.assertAlmostEqual(right[0], 0.0, places=12)
        self.assertAlmostEqual(right[1], -1.0, places=12)
        self.assertAlmostEqual(right[2], 0.0, places=12)

        # Image-down is perpendicular to the centre ray and points downward.
        down = mount.optical_down_body
        centre = mount.optical_axis_body
        dot = sum(left * right for left, right in zip(down, centre))
        self.assertAlmostEqual(dot, 0.0, places=12)
        self.assertLess(down[2], 0.0)

    def test_stream_metadata_is_preserved(self) -> None:
        self.assertEqual(self.geometry.update_rate_hz, 5.0)
        self.assertEqual(self.geometry.near_clip_m, 0.1)
        self.assertEqual(self.geometry.far_clip_m, 200.0)


if __name__ == "__main__":
    unittest.main()
