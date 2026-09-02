import json
from pathlib import Path

from tools.prepare_labelme_switch_review import (
    diverse_sample,
    evenly_spaced,
    read_detection_shapes,
    validate_document,
)


def test_detection_box_becomes_labelme_rectangle(tmp_path: Path):
    label = tmp_path / "draft.txt"
    label.write_text("0 0.5 0.5 0.2 0.4\n", encoding="utf-8")

    shapes = read_detection_shapes(label, width=1000, height=500)

    assert shapes[0]["label"] == "switch"
    assert shapes[0]["shape_type"] == "rectangle"
    assert shapes[0]["points"] == [[400.0, 150.0], [600.0, 350.0]]


def test_evenly_spaced_includes_both_ends_without_duplicates():
    items = [{"image": str(index)} for index in range(10)]

    selected = evenly_spaced(items, 4)

    assert [row["image"] for row in selected] == ["0", "3", "6", "9"]


def test_diverse_sample_round_robins_across_sequences():
    rows = [
        {"image": "train/001__alpha_0001.jpg"},
        {"image": "train/002__alpha_0002.jpg"},
        {"image": "train/003__beta_0001.jpg"},
        {"image": "train/004__beta_0002.jpg"},
    ]

    selected = diverse_sample(rows, 3)

    assert [row["image"] for row in selected] == [
        "train/001__alpha_0001.jpg",
        "train/003__beta_0001.jpg",
        "train/002__alpha_0002.jpg",
    ]


def test_reviewed_negative_is_valid_but_polygon_is_not(tmp_path: Path):
    negative = tmp_path / "negative.json"
    negative.write_text(
        json.dumps({"flags": {"reviewed": True}, "shapes": []}), encoding="utf-8"
    )
    assert validate_document(negative) == (True, [])

    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        json.dumps(
            {
                "flags": {"reviewed": True},
                "shapes": [
                    {"label": "switch", "shape_type": "polygon", "points": [[0, 0]]}
                ],
            }
        ),
        encoding="utf-8",
    )
    assert validate_document(invalid) == (True, ["switch_requires_rectangle"])
