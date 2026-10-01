from app.models import Hold, Segment
from app.voice import split_take

SEGS = [Segment(scene_id="a", start=0, end=10), Segment(scene_id="b", start=10, end=25),
        Segment(scene_id="c", start=25, end=30)]


def as_tuples(parts):
    return [(p.scene_id, p.start, p.end, [(h.at, h.duration) for h in p.holds]) for p in parts]


def test_no_pauses_splits_on_scene_boundaries():
    assert as_tuples(split_take(SEGS, 0, [], 30.0)) == [
        ("a", 0, 10, []), ("b", 10, 25, []), ("c", 25, None, [])]


def test_pauses_shift_later_scenes_and_stay_in_their_scene():
    holds = [Hold(at=4, duration=3), Hold(at=10, duration=2), Hold(at=20, duration=5), Hold(at=30, duration=4)]
    assert as_tuples(split_take(SEGS, 0, holds, 44.0)) == [
        # A pause exactly at a boundary belongs to the scene that just ended.
        ("a", 0, 15, [(4, 3), (10, 2)]),
        ("b", 15, 35, [(10, 5)]),
        # Talking on after the animation ended is a pause at the end of the last scene.
        ("c", 35, None, [(5, 4)]),
    ]


def test_recording_from_a_later_scene():
    holds = [Hold(at=3, duration=9), Hold(at=12, duration=1)]  # the first is before the start: ignored
    assert as_tuples(split_take(SEGS, 1, holds, 21.0)) == [("b", 0, 16, [(2, 1)]), ("c", 16, None, [])]


def test_stopping_early_leaves_later_scenes_alone():
    assert as_tuples(split_take(SEGS, 0, [Hold(at=5, duration=2)], 14.0)) == [
        ("a", 0, 12, [(5, 2)]), ("b", 12, None, [])]
