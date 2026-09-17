import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GAZEBO_DIR = REPO_ROOT / "simulation" / "gazebo"
WORLD_PATH = GAZEBO_DIR / "worlds" / "rail_demo_realistic.sdf"
CAMERA_MODEL_PATH = GAZEBO_DIR / "models" / "x500_mono_cam" / "model.sdf"
START_SCRIPT = REPO_ROOT / "scripts" / "start_realistic_rail_sitl.sh"


class RailFlightSetupTests(unittest.TestCase):
    def test_launch_pad_and_vehicle_start_on_track_centerline(self) -> None:
        root = ET.parse(WORLD_PATH).getroot()
        pad = root.find("./world/model[@name='launch_pad']")
        self.assertIsNotNone(pad)
        assert pad is not None
        pose = [float(value) for value in pad.findtext("pose", "").split()]
        self.assertEqual(pose[:2], [-16.85, 0.0])

        script = START_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("-16.85,0,0.2,0,0,0", script)
        self.assertIn("make px4_sitl gz_x500_mono_cam", script)

    def test_camera_is_fixed_forward_down_at_35_degrees(self) -> None:
        root = ET.parse(CAMERA_MODEL_PATH).getroot()
        model = root.find("model")
        self.assertIsNotNone(model)
        assert model is not None
        camera_include = next(
            include
            for include in model.findall("include")
            if include.findtext("uri") == "model://mono_cam"
        )
        pose = [float(value) for value in camera_include.findtext("pose", "").split()]
        self.assertAlmostEqual(pose[4], 0.61086523820)

        joint_pose = model.findtext("./joint[@name='CameraJoint']/pose", "")
        self.assertEqual(camera_include.findtext("pose"), joint_pose)


if __name__ == "__main__":
    unittest.main()