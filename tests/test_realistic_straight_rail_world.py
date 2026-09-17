import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GAZEBO_DIR = REPO_ROOT / "simulation" / "gazebo"
MODEL_DIR = GAZEBO_DIR / "models" / "railway_straight_realistic"
WORLD_PATH = GAZEBO_DIR / "worlds" / "rail_demo_realistic.sdf"


class RealisticStraightRailWorldTests(unittest.TestCase):
    def test_world_contains_only_eight_straight_track_modules(self) -> None:
        root = ET.parse(WORLD_PATH).getroot()
        world = root.find("world")
        self.assertIsNotNone(world)
        assert world is not None

        track_includes = [
            include
            for include in world.findall("include")
            if include.findtext("uri") == "model://railway_straight_realistic"
        ]
        self.assertEqual(len(track_includes), 8)
        self.assertEqual(
            [float(include.findtext("pose", "").split()[0]) for include in track_includes],
            [-14.0, -10.0, -6.0, -2.0, 2.0, 6.0, 10.0, 14.0],
        )

        serialized = ET.tostring(world, encoding="unicode").lower()
        self.assertNotIn("turnout", serialized)
        self.assertNotIn("intersection", serialized)
        self.assertNotIn("snow", serialized)

    def test_model_uses_part_one_glb_as_visual_only(self) -> None:
        root = ET.parse(MODEL_DIR / "model.sdf").getroot()
        visual_uri = root.findtext("./model/link/visual/geometry/mesh/uri")
        self.assertEqual(
            visual_uri,
            "model://railway_straight_realistic/meshes/straight_track.glb",
        )
        self.assertIsNone(root.find("./model/link/collision"))

        mesh_path = MODEL_DIR / "meshes" / "straight_track.glb"
        self.assertTrue(mesh_path.is_file())
        self.assertGreater(mesh_path.stat().st_size, 1_000_000)


if __name__ == "__main__":
    unittest.main()
