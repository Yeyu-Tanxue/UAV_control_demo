from __future__ import annotations

import unittest

from tools.select_rail_annotation_batch import select_batch


def make_row(split: str, sequence: str, frame: int, hint: str = "normal") -> dict[str, str]:
    return {
        "image_path": f"imgs/session/{sequence}/frame_{frame:08d}.jpg",
        "annotation_path": f"annots/session/{sequence}/frame_{frame:08d}.xml",
        "sequence_id": f"session/{sequence}",
        "frame_id": str(frame),
        "split": split,
        "camera_height_m": "2.45",
        "person_count": str(frame % 3),
        "bicycle_count": "0",
        "scenario_hint": hint,
    }


class SelectRailAnnotationBatchTests(unittest.TestCase):
    def test_exact_quota_sequence_coverage_and_holdout_modes(self) -> None:
        candidates: list[dict[str, str]] = []
        for split, sequence_count in (("train", 4), ("val", 2), ("test", 2)):
            for sequence_index in range(sequence_count):
                hint = "switch_review" if split == "train" and sequence_index == 0 else "normal"
                candidates.extend(
                    make_row(split, f"{split}_{sequence_index}.mp4", frame * 10, hint)
                    for frame in range(6)
                )

        selected = select_batch(candidates, {"train": 11, "val": 4, "test": 4})
        self.assertEqual(len(selected), 19)
        self.assertEqual(sum(row["split"] == "train" for row in selected), 11)
        self.assertEqual(sum(row["split"] == "val" for row in selected), 4)
        self.assertEqual(sum(row["split"] == "test" for row in selected), 4)
        train_sequences = {row["sequence_id"] for row in selected if row["split"] == "train"}
        self.assertEqual(len(train_sequences), 4)
        for sequence in train_sequences:
            self.assertGreaterEqual(
                sum(row["sequence_id"] == sequence for row in selected), 2
            )
        self.assertTrue(
            all(
                row["annotation_mode"] == "manual_ground_truth"
                for row in selected
                if row["split"] in {"val", "test"}
            )
        )
        self.assertEqual(len({row["image_path"] for row in selected}), len(selected))
        self.assertEqual(
            [int(row["batch_order"]) for row in selected], list(range(1, 20))
        )

    def test_rejects_train_quota_that_cannot_cover_every_sequence(self) -> None:
        candidates = [
            make_row("train", f"train_{index}.mp4", 0) for index in range(4)
        ]
        candidates.extend(make_row("val", "val.mp4", index) for index in range(2))
        candidates.extend(make_row("test", "test.mp4", index) for index in range(2))
        with self.assertRaises(ValueError):
            select_batch(candidates, {"train": 3, "val": 1, "test": 1})


if __name__ == "__main__":
    unittest.main()
