from datetime import date

import pytest

from daemonhive.agents.fitness.parser import ParseError, parse_line, parse_session

LOG = """Push 2026-11-03
Bench Press 120kg 3x3 RPE 7
Incline DB Press 32.5kg 3x10 @8
Dips BW+20kg 4x8
OHP 60kg 5,5,4
# felt flat today
"""


def test_reference_log() -> None:
    s = parse_session(LOG)
    assert (s.kind, s.day) == ("push", date(2026, 11, 3))
    assert [e.name for e in s.exercises] == [
        "bench press",
        "incline dumbbell press",
        "dips",
        "overhead press",
    ]
    bench = s.exercise("bench press")
    assert bench and len(bench.sets) == 3 and bench.sets[0].rpe == 7
    assert bench.volume_kg == 120 * 9
    assert s.notes == ["felt flat today"]


@pytest.mark.parametrize(
    ("line", "name", "weight", "reps"),
    [
        ("Bench Press 120kg 3x8", "bench press", 120, [8, 8, 8]),
        ("bench 100kg 5x5", "bench press", 100, [5] * 5),
        ("BP 225lb 1x5", "bench press", 102.06, [5]),
        ("Squat 140kg 5,5,3", "back squat", 140, [5, 5, 3]),
        ("DL 180kg 1 x 3 RPE 9.5", "deadlift", 180, [3]),
        ("Pull Ups BW 3x10", "pull ups", 0, [10] * 3),
        ("Pull Ups BW+10kg 3x6", "pull ups", 10, [6] * 3),
        ("Lateral Raise 12.5kg 3x15 @9", "lateral raise", 12.5, [15] * 3),
    ],
)
def test_line_variants(line: str, name: str, weight: float, reps: list[int]) -> None:
    ex = parse_line(line)
    assert ex.name == name
    assert ex.sets[0].weight_kg == pytest.approx(weight, abs=0.01)
    assert [s.reps for s in ex.sets] == reps


def test_bodyweight_flag() -> None:
    assert parse_line("Dips BW 3x10").sets[0].bodyweight


@pytest.mark.parametrize(
    "bad",
    ["Bench Press heavy", "Bench 120kg", "Bench 120kg 0x5", "Bench 120kg 30x1", "120kg 3x5"],
)
def test_rejects_garbage(bad: str) -> None:
    with pytest.raises(ParseError):
        parse_line(bad)


def test_session_needs_header_and_exercises() -> None:
    with pytest.raises(ParseError):
        parse_session("Bench 100kg 3x5")
    with pytest.raises(ParseError):
        parse_session("Push 2026-11-03\n# only notes")


def test_repeated_exercise_lines_merge() -> None:
    s = parse_session("Push 2026-11-03\nBench 100kg 1x5\nBench 90kg 2x8")
    assert len(s.exercises) == 1 and len(s.exercises[0].sets) == 3
