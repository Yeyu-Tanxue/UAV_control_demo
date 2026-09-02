from collections import Counter

from tools.prepare_l4r_switch_yolo import (
    CLASS_IDS,
    _assign_stratified_blocks,
    _output_class_id,
    _switch_box,
)


def test_switch_box_normalizes_reversed_marks():
    class_id, box, reason = _switch_box(
        {
            "kind": "fork",
            "direction": "right",
            "marks": [{"x": 120, "y": 80}, {"x": 20, "y": 30}],
        },
        width=200,
        height=100,
    )

    assert class_id == CLASS_IDS["fork_right"]
    assert box == (20.0, 30.0, 120.0, 80.0)
    assert reason == "usable"


def test_switch_box_rejects_missing_marks():
    assert _switch_box({"kind": "merge", "direction": "left"}, 200, 100) == (
        None,
        None,
        "invalid_marks",
    )


def test_kind_mode_collapses_directions_but_keeps_topology():
    assert _output_class_id(CLASS_IDS["fork_right"], "kind") == 0
    assert _output_class_id(CLASS_IDS["merge_unknown"], "kind") == 1
    assert _output_class_id(CLASS_IDS["fork_right"], "detailed") == CLASS_IDS["fork_right"]


def test_single_mode_collapses_all_switch_types():
    assert _output_class_id(CLASS_IDS["fork_left"], "single") == 0
    assert _output_class_id(CLASS_IDS["merge_right"], "single") == 0


def test_stratified_split_keeps_blocks_intact_and_uses_expected_capacity():
    stats = {
        f"winter:block_{index:04d}": Counter(
            images=100,
            positive_images=20 if index < 4 else 1,
            fork_left=10 if index < 4 else 0,
            merge_unknown=10 if index < 4 else 1,
        )
        for index in range(20)
    }

    assignments = _assign_stratified_blocks(stats, seed=7)

    assert set(assignments) == set(stats)
    assert Counter(assignments.values()) == Counter(train=16, val=2, test=2)
    assert all(value in {"train", "val", "test"} for value in assignments.values())
