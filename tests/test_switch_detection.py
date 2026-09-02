from tools.switch_detection import _class_agnostic_nms, _is_fork_name


def test_class_agnostic_nms_suppresses_same_box_across_classes():
    boxes = [
        [10.0, 10.0, 30.0, 30.0],
        [10.0, 10.0, 30.0, 30.0],
        [50.0, 50.0, 70.0, 70.0],
    ]
    confidences = [0.6, 0.9, 0.7]

    assert _class_agnostic_nms(boxes, confidences, 0.5) == [1, 2]


def test_fork_name_supports_detailed_and_kind_modes():
    assert _is_fork_name("fork")
    assert _is_fork_name("fork_left")
    assert not _is_fork_name("merge")
