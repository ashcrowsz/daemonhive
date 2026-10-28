from daemonhive.agents.fitness.analysis import Signal, compare, describe, estimated_1rm, regressions
from daemonhive.agents.fitness.parser import parse_session

LAST = parse_session("Push 2026-10-27\nBench Press 120kg 3x8\nOHP 60kg 3x8")
TODAY = parse_session("Push 2026-11-03\nBench Press 120kg 3x3\nOHP 62.5kg 3x8\nDips BW 3x10")


def test_reference_regression_is_detected() -> None:
    deltas = {d.exercise: d for d in compare(LAST, TODAY)}
    bench = deltas["bench press"]
    assert bench.signal is Signal.regression
    assert round(bench.volume_change, 3) == -0.625
    assert describe(bench) == "Bench Press volume dropped 62%"


def test_pr_and_new_exercise() -> None:
    deltas = {d.exercise: d for d in compare(LAST, TODAY)}
    assert deltas["overhead press"].signal is Signal.pr
    assert deltas["dips"].signal is Signal.new
    assert [d.exercise for d in regressions(list(deltas.values()))] == ["bench press"]


def test_first_session_ever() -> None:
    assert all(d.signal is Signal.new for d in compare(None, TODAY))


def test_small_dip_is_not_a_regression() -> None:
    a = parse_session("Legs 2026-11-01\nSquat 140kg 5x5")
    b = parse_session("Legs 2026-11-08\nSquat 140kg 5,5,5,5,4")
    assert compare(a, b)[0].signal is Signal.steady


def test_epley() -> None:
    assert estimated_1rm(100, 1) == 100
    assert round(estimated_1rm(100, 10), 1) == 133.3
