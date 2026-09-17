import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SENSOR_MODEL_PATH = (
    REPO_ROOT / "simulation" / "gazebo" / "models" / "mono_cam" / "model.sdf"
)


class RailCameraSensorTests(unittest.TestCase):
    def test_camera_stream_is_low_load_but_cnn_usable(self) -> None:
        root = ET.parse(SENSOR_MODEL_PATH).getroot()
        sensor = root.find("./model/link/sensor[@name='imager']")
        self.assertIsNotNone(sensor)
        assert sensor is not None
        self.assertEqual(sensor.findtext("./camera/image/width"), "640")
        self.assertEqual(sensor.findtext("./camera/image/height"), "480")
        self.assertAlmostEqual(
            float(sensor.findtext("./camera/horizontal_fov", "0")),
            1.91986217719,
        )
        self.assertEqual(sensor.findtext("update_rate"), "5")
        self.assertEqual(sensor.findtext("visualize"), "false")


if __name__ == "__main__":
    unittest.main()
