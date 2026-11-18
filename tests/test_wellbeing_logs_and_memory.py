from datetime import date

import pytest

from daemonhive.agents.concierge.routing import route_by_rules
from daemonhive.agents.wellbeing.logs import LogError, parse_log
from daemonhive.mcp.graph_store import add_fact_queries, rel_type

TODAY = date(2026, 11, 3)


@pytest.mark.parametrize(
    ("text", "night", "hours"),
    [
        ("slept 5.5h", date(2026, 11, 2), 5.5),
        ("Slept 7h30", date(2026, 11, 2), 7.5),
        ("2026-11-01 slept 5h", date(2026, 11, 1), 5.0),
        ("sleep 6 h, woke up twice", date(2026, 11, 2), 6.0),
    ],
)
def test_sleep_lines(text: str, night: date, hours: float) -> None:
    p = parse_log(text, TODAY)
    assert p.sleep and (p.sleep.night_of, p.sleep.hours) == (night, hours)


def test_meal_lines() -> None:
    p = parse_log("lunch chicken rice 750 kcal", TODAY)
    assert p.meal and (p.meal.day, p.meal.kcal, p.label) == (TODAY, 750, "lunch chicken rice")
    p = parse_log("2026-11-02 dinner pasta 900kcal", TODAY)
    assert p.meal and (p.meal.day, p.meal.kcal) == (date(2026, 11, 2), 900)


@pytest.mark.parametrize("bad", ["slept 40h", "dinner 9000 kcal", "had a great day"])
def test_rejects_implausible_or_unknown(bad: str) -> None:
    with pytest.raises(LogError):
        parse_log(bad, TODAY)


def test_dated_logs_still_route_at_tier0() -> None:
    for text in ("2026-11-01 slept 5h", "2026-11-02 dinner pasta 900 kcal"):
        r = route_by_rules(text)
        assert r is not None and r.agents == ("wellbeing",)
    r = route_by_rules("plan my day")
    assert r is not None and r.agents == ("work",)


def test_cypher_closes_single_valued_facts_only() -> None:
    weight = add_fact_queries("Person:me", "HAS_WEIGHT", "80kg")
    assert len(weight) == 2 and "SET old.valid_to" in weight[0]
    link = add_fact_queries("Session:push:2026-11-03", "AFFECTED_BY", "SleepDeficit")
    assert len(link) == 1 and "[r:AFFECTED_BY" in link[0]


@pytest.mark.parametrize("bad", ["AFFECTED_BY]->() DETACH DELETE n //", "lower", "A B"])
def test_relation_type_is_validated(bad: str) -> None:
    with pytest.raises(ValueError):
        rel_type(bad)
