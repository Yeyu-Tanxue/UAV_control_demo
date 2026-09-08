import importlib.util
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPO_ROOT / "tools" / "generate_gazebo_rail_world.py"
SPEC = importlib.util.spec_from_file_location("generate_gazebo_rail_world", GENERATOR_PATH)
assert SPEC and SPEC.loader
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class GazeboRailWorldTests(unittest.TestCase):
    def test_generated_files_are_current(self) -> None:
        for path, expected in GENERATOR.output_files(REPO_ROOT).items():
            self.assertTrue(path.exists(), path)
            self.assertEqual(path.read_text(encoding="utf-8"), expected)

    def test_track_has_standard_gauge_and_expected_sleepers(self) -> None:
        root = ET.fromstring(GENERATOR.build_track_model())
        link = root.find("./model/link")
        self.assertIsNotNone(link)
        assert link is not None

        sleepers = [
            visual
            for visual in link.findall("visual")
            if visual.attrib["name"].startswith("sleeper_")
        ]
        self.assertEqual(len(sleepers), GENERATOR.SLEEPER_COUNT)

        left_pose = link.findtext("./visual[@name='rail_left_visual']/pose")
        right_pose = link.findtext("./visual[@name='rail_right_visual']/pose")
        self.assertIsNotNone(left_pose)
        self.assertIsNotNone(right_pose)
        assert left_pose and right_pose
        center_distance = float(left_pose.split()[1]) - float(right_pose.split()[1])
        inner_face_gauge = center_distance - GENERATOR.RAIL_WIDTH_M
        self.assertAlmostEqual(inner_face_gauge, 1.435, places=4)

    def test_world_references_track_and_keeps_launch_pad_clear(self) -> None:
        root = ET.fromstring(GENERATOR.build_world())
        world = root.find("world")
        self.assertIsNotNone(world)
        assert world is not None
        self.assertEqual(world.attrib["name"], "rail_demo")
        self.assertEqual(world.findtext("./include/uri"), "model://rail_track")
        self.assertEqual(world.findtext("./model[@name='launch_pad']/pose"), "-13 -3 0.06 0 0 0")


if __name__ == "__main__":
    unittest.main()
