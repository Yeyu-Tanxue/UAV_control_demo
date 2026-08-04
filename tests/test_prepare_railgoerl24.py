from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from tools.prepare_railgoerl24 import (
    assign_sequence_splits,
    evenly_spaced_rows,
    parse_annotation,
    prepare,
)


XML_TEMPLATE = """<annotation>
  <filename>{filename}</filename>
  <size><width>100</width><height>50</height><depth>3</depth></size>
  <everythingAnnotated>partial</everythingAnnotated>
  {objects}
</annotation>
"""


def object_xml(labels: list[str], box: tuple[int, int, int, int] = (1, 2, 30, 40)) -> str:
    names = "".join(f"<name>{label}</name>" for label in labels)
    xmin, ymin, xmax, ymax = box
    return (
        "<object><classes>"
        + names
        + "</classes><bndbox>"
        + f"<xmin>{xmin}</xmin><ymin>{ymin}</ymin>"
        + f"<xmax>{xmax}</xmax><ymax>{ymax}</ymax>"
        + "</bndbox></object>"
    )


class PrepareRailGoerl24Tests(unittest.TestCase):
    def test_parse_multilabel_and_invalid_box(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.xml"
            path.write_text(
                XML_TEMPLATE.format(
                    filename="sample.jpg",
                    objects=object_xml(["person", "bicycle"])
                    + object_xml(["person"], (20, 5, 10, 30)),
                ),
                encoding="utf-8",
            )
            parsed = parse_annotation(path)
        self.assertEqual(parsed.object_count, 2)
        self.assertEqual(parsed.class_assignment_count, 3)
        self.assertEqual(parsed.label_counts, {"bicycle": 1, "person": 2})
        self.assertEqual(parsed.invalid_box_count, 1)

    def test_split_is_deterministic_and_sequence_safe(self) -> None:
        sizes = {f"sequence-{index}": index + 10 for index in range(12)}
        first = assign_sequence_splits(sizes, seed=7)
        second = assign_sequence_splits(sizes, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(set(first), set(sizes))
        self.assertEqual(set(first.values()), {"train", "val", "test"})

    def test_even_sampling_has_no_duplicates(self) -> None:
        rows = [{"frame_id": index} for index in range(101)]
        selected = evenly_spaced_rows(rows, 8)
        ids = [row["frame_id"] for row in selected]
        self.assertEqual(len(ids), 8)
        self.assertEqual(len(set(ids)), 8)
        self.assertGreater(min(ids), 0)
        self.assertLess(max(ids), 100)

    def test_prepare_ignores_auto_annotations_and_writes_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Annotated_RGB_data"
            output = Path(temp) / "output"
            for sequence in ("alpha.mp4", "beta.mp4", "gamma.mp4"):
                image_dir = root / "imgs" / "session" / sequence
                annotation_dir = root / "annots" / "session" / sequence
                auto_dir = root / "annots" / "session" / f"{sequence}_auto_annots"
                image_dir.mkdir(parents=True)
                annotation_dir.mkdir(parents=True)
                auto_dir.mkdir(parents=True)
                for frame in range(3):
                    stem = f"frame_{frame:08d}"
                    (image_dir / f"{stem}.jpg").write_bytes(b"not-decoded")
                    xml = XML_TEMPLATE.format(
                        filename=f"{stem}.jpg",
                        objects=object_xml(["person"]) if frame else "",
                    )
                    (annotation_dir / f"{stem}.xml").write_text(xml, encoding="utf-8")
                    (auto_dir / f"{stem}.xml").write_text(xml, encoding="utf-8")

            report = prepare(root, output, candidate_frames_per_sequence=2, seed=9, strict=True)
            with (output / "dataset_manifest.csv").open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                manifest = list(csv.DictReader(handle))
            with (output / "rail_annotation_candidates.csv").open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                candidates = list(csv.DictReader(handle))

        self.assertEqual(report["image_count"], 9)
        self.assertEqual(report["manual_xml_count"], 9)
        self.assertFalse(report["auto_annotations_used"])
        self.assertEqual(len(candidates), 6)
        self.assertTrue(all(not Path(row["image_path"]).is_absolute() for row in manifest))
        self.assertTrue(all("_auto_annots" not in row["annotation_path"] for row in manifest))
        sequence_splits: dict[str, set[str]] = {}
        for row in manifest:
            sequence_splits.setdefault(row["sequence_id"], set()).add(row["split"])
        self.assertTrue(all(len(splits) == 1 for splits in sequence_splits.values()))


if __name__ == "__main__":
    unittest.main()
