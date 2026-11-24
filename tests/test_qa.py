"""The chatbot: questions are routed to the owning agent and answered from its data."""

import asyncio
import json
from datetime import date, timedelta

from daemonhive.agents.concierge.routing import route_by_rules
from daemonhive.agents.fitness.parser import Exercise, Session, SetEntry
from daemonhive.agents.fitness.qa import FitnessQA
from daemonhive.agents.wellbeing.qa import WellbeingQA
from daemonhive.agents.wellbeing.recovery import MealRow, SleepRow
from daemonhive.common.agentic import Tool, parse_reply, run_agent
from daemonhive.common.tiers import Tier

TODAY = date(2026, 3, 1)


def s(kind: str, day: str, *ex: tuple[str, float, list[int]]) -> Session:
    return Session(
        kind,
        date.fromisoformat(day),
        [Exercise(n, [SetEntry(w, r) for r in reps]) for n, w, reps in ex],
    )


HISTORY = [
    s("push", "2026-01-05", ("bench press", 100, [8, 8])),
    s("lower", "2026-01-06", ("back squat", 120, [5, 5]), ("leg extension", 60, [10])),
    s("push", "2026-01-12", ("bench press", 105, [8, 8])),
    s("lower", "2026-01-13", ("back squat", 130, [5, 5])),
    s("push", "2026-01-19", ("bench press", 110, [6, 6])),
    s("push", "2026-01-26", ("bench press", 115, [6, 5]), ("pec deck", 0, [10])),
    s("lower", "2026-01-27", ("back squat", 140, [5]), ("deadlift", 200, [1])),
    s("push", "2026-02-02", ("bench press", 100, [3])),  # a bad day
]


def ask(q: str, **kw):
    return asyncio.run(FitnessQA(HISTORY, TODAY, **kw).answer(q))


def test_questions_route_to_the_owner_on_its_ask_skill() -> None:
    r = route_by_rules("what's my last PR?")
    assert r and r.agents == ("fitness",) and r.skill == "ask" and r.tier == Tier.code
    r = route_by_rules("how did I sleep this week?")
    assert r and r.agents == ("wellbeing",) and r.skill == "ask"
    r = route_by_rules("did my bench drop because I ate too little?")
    assert r and r.agents == ("fitness",)  # cross-domain: Fitness, which can read the flags
    assert route_by_rules("slept 7h").skill == ""  # a log, not a question
    assert route_by_rules("plan my day").agents == ("work",)


def test_last_pr_and_last_session_by_kind() -> None:
    a = ask("what's my last PR?")
    assert a.tier == Tier.code and a.tool == "last_pr"
    assert "Tue 27 Jan 2026" in a.text and "back squat 140 kg x 5" in a.text
    a = ask("what did I do last push workout?")
    assert a.tool == "last_session" and "Mon 2 Feb 2026" in a.text and "1x3 @ 100 kg" in a.text
    a = ask("what was my last leg day?")
    assert "Lower on Tue 27 Jan 2026" in a.text and "deadlift" in a.text


def test_bests_progression_and_last_time() -> None:
    assert "115 kg x 6" in ask("what's my best bench?").text
    p = ask("how is my squat progressing?")
    assert p.tool == "progression" and "back squat".title() in p.text
    t = ask("when did I last deadlift?")
    assert t.tool == "last_time" and "Tue 27 Jan 2026" in t.text
    # a load written as "Max" can't be compared: no fake PR from it
    assert "pec deck" not in ask("last PR").text


def test_why_reads_the_memory_links() -> None:
    async def memory(key: str):
        assert key == "Session:push:2026-02-02"
        props = json.dumps({"last_night_h": 4.0, "avg_sleep_h": 6.0, "kcal_vs_target": -550})
        return [
            {"relation": "AFFECTED_BY", "object": "SleepDeficit", "props": props},
            {"relation": "AFFECTED_BY", "object": "CalorieDeficit", "props": props},
        ]

    a = ask("why did my lifts drop?", memory_search=memory)
    assert "Mon 2 Feb 2026" in a.text and "bench press" in a.text
    assert "last night 4.0 h" in a.text and "-550 kcal/day" in a.text


class FakeModel:
    """Plays the model's side of the tool protocol."""

    def __init__(self, replies: list[str]) -> None:
        self.replies, self.seen = replies, []

    async def ask(self, system, user, tier=Tier.large, max_tokens=600) -> str:
        self.seen.append(user)
        return self.replies.pop(0)


def test_unrecognised_question_goes_through_the_tool_loop() -> None:
    model = FakeModel(
        [
            '```json\n{"tool": "best", "args": {"exercise": "squat"}}\n```',
            '{"answer": "Your best squat is 140 kg x 5."}',
        ]
    )
    a = asyncio.run(FitnessQA(HISTORY, TODAY).answer("which of my lifts am I proudest of?", model))
    assert a.tier == Tier.large and a.text == "Your best squat is 140 kg x 5."
    assert a.steps == [{"tool": "best", "args": {"exercise": "squat"}}]
    assert "140 kg x 5" in model.seen[1]  # the model saw the tool's real numbers


def test_tool_loop_survives_bad_tools_and_prose() -> None:
    async def boom(**_):
        raise ValueError("bad day")

    tools = [Tool("t", "x", {"day": "d"}, boom)]
    model = FakeModel(
        ['{"tool": "nope"}', '{"tool": "t", "args": {"day": "x"}}', "Sorry, I can't tell."]
    )
    run = asyncio.run(run_agent("q", tools, model, "2026-03-01"))
    assert run.answer == "Sorry, I can't tell." and "bad day" in model.seen[-1]
    assert parse_reply('Sure! {"answer": "a {b}"} hope that helps') == {"answer": "a {b}"}


def test_wellbeing_answers() -> None:
    sleep = [
        SleepRow(TODAY - timedelta(days=i), h) for i, h in enumerate([7, 7, 4, 7, 7, 7, 7, 7], 1)
    ]
    meals = [MealRow(TODAY - timedelta(days=i), 1900) for i in range(1, 9)]

    async def person():
        return [
            {
                "relation": "IN_PHASE",
                "object": "Phase:cut",
                "valid_from": "2026-01-04",
                "valid_to": None,
            }
        ]

    qa = WellbeingQA(
        sleep, meals, [(date(2025, 10, 26), 100.5), (date(2026, 2, 1), 96.0)], TODAY, 1950, person
    )
    a = asyncio.run(qa.answer("how did I sleep this week?"))
    assert a.tier == Tier.code and "1 night(s) under 6 h" in a.text and "shortest 4 h" in a.text
    assert "1900 kcal/day" in asyncio.run(qa.answer("what did I eat on average last 7 days?")).text
    assert "96 kg" in asyncio.run(qa.answer("what's my weight?")).text
    assert "cut since 2026-01-04" in asyncio.run(qa.answer("am I cutting?")).text
