from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.prepare_l4r_nlb_yolo import (
    ego_polygon,
    has_proper_self_intersection,
    prepare,
    yolo_line,
)


def track(position: str, left: list[tuple[int, int]], right: list[tuple[int, int]]) -> dict:
    return {
        "relative position": position,
        "left rail": {"points": [{"x": x, "y": y} for x, y in left]},
        "right rail": {"points": [{"x": x, "y": y} for x, y in right]},
    }


class PrepareL4RNLBYoloTests(unittest.TestCase):
    def test_ego_polygon_selects_only_ego_and_clips(self) -> None:
        data = {
            "tracks": {
                "0": track("ego", [(-2, 10), (40, 90)], [(80, 10), (120, 90)]),
                "1": track("left", [(1, 1), (2, 9)], [(3, 1), (4, 9)]),
            }
        }
        polygon, reason, count = ego_polygon(data, width=100, height=100)
        self.assertEqual(reason, "usable")
        self.assertEqual(count, 1)
        self.assertEqual(
            polygon, [(0.0, 10.0), (40.0, 90.0), (99.0, 90.0), (80.0, 10.0)]
        )
        line = yolo_line(polygon or [], 100, 100)
        self.assertTrue(line.startswith("0 0.000000 0.100000"))

    def test_missing_ego_is_excluded(self) -> None:
        polygon, reason, count = ego_polygon(
            {"tracks": {"0": track("left", [(1, 1), (2, 9)], [(3, 1), (4, 9)])}},
            10,
            10,
        )
        self.assertIsNone(polygon)
        self.assertEqual(reason, "ego_track_count_0")
        self.assertEqual(count, 0)

    def test_self_intersection_is_detected(self) -> None:
        self.assertTrue(
            has_proper_self_intersection(
                [(0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0)]
            )
        )
        polygon, reason, _ = ego_polygon(
            {
                "tracks": {
                    "0": track(
                        "ego",
                        [(0, 0), (90, 90)],
                        [(90, 0), (0, 90)],
                    )
                }
            },
            100,
            100,
        )
        self.assertIsNone(polygon)
        self.assertEqual(reason, "self_intersecting_polygon")

    def test_prepare_writes_yolo_pairs_and_keeps_blocks_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            output = Path(temp) / "output"
            for directory in ("images", "annotations", "masks"):
                (source / directory).mkdir(parents=True)
            for frame in range(0, 1200, 40):
                stem = f"nlb_winter_{frame:06d}"
                (source / "images" / f"{stem}.png").write_bytes(b"image")
                (source / "masks" / f"{stem}.png").write_bytes(b"mask")
                data = {
                    "tracks": {
                        "0": track(
                            "ego",
                            [(800, 400), (700, 1079)],
                            [(1000, 400), (1200, 1079)],
                        )
                    },
                    "switches": {},
                    "tag groups": {"weather": ["snow"]},
                }
                (source / "annotations" / f"{stem}.json").write_text(
                    json.dumps(data), encoding="utf-8"
                )

            report = prepare(source, output, block_size=200, seed=4, materialize_mode="copy")
            labels = list((output / "labels").rglob("*.txt"))
            images = list((output / "images").rglob("*.png"))

        self.assertEqual(report["usable_count"], 30)
        self.assertEqual(len(labels), 30)
        self.assertEqual(len(images), 30)
        self.assertEqual(set(report["splits"]), {"train", "val", "test"})
        self.assertEqual(sum(item["images"] for item in report["splits"].values()), 30)


if __name__ == "__main__":
    unittest.main()
