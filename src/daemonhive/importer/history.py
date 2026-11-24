"""Parse a free-text training diary (the kind you type in a notes app) into sessions.

Real logs are messy, so this is deliberately forgiving:

    March 9: Pull                         <- header: date + optional kind
    Latpulldown 93kg 2x8-7                <- 2 sets: 8 reps then 7
    Flat Press 5 Plates 1x5, 4 Plates 1x5 <- load we can't convert -> kept as text
    Triceps Pushdown Max + 12.3kg 1x7     <- "Max" = the whole stack
    Deadlift:                             <- exercise name on its own line...
    Top set 180kg x1                      <- ...sets follow on the next lines
    Upper:                                <- header with no date -> date interpolated
    Next Lower: Deadlift 180kg 1x3        <- a plan, not a workout -> skipped

Anything that isn't a set (cardio, steps, notes, phases) is kept as a note or an event.
No model is involved: tier 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from daemonhive.agents.fitness.parser import Exercise, Session, SetEntry, normalize_name

MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ]
    )
    for m in names
}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_MD = re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.IGNORECASE)
DATE_DM = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH})\b", re.IGNORECASE)
SET_RE = re.compile(r"(\d+)\s*x\s*(\d+(?:[.,]\d+)?(?:\s*-\s*\d+(?:[.,]\d+)?)*)", re.IGNORECASE)
XREPS = re.compile(r"(?<![\dx])\s*x\s*(\d+)\b", re.IGNORECASE)  # "180kg x1" = one set of 1
KG = re.compile(r"(\d+(?:[.,]\d+)?)\s*kg\b", re.IGNORECASE)
RPE = re.compile(r"rpe\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)
KCAL = re.compile(r"(\d{3,4})\s*kcal", re.IGNORECASE)
BODYWEIGHT = re.compile(r"\b(\d{2,3}(?:[.,]\d)?)\s*kg\s*$", re.IGNORECASE)

KINDS = {
    "push": "push",
    "pull": "pull",
    "upper": "upper",
    "lower": "lower",
    "legs": "lower",
    "anterior": "anterior",
    "full body": "full body",
    "calisthenics": "calisthenics",
    "chest and back": "upper",
    "shoulders and arms": "arms",
    "deadlift and arms": "deadlift",
    "deadlift and misc": "deadlift",
    "deadlift and shoulders": "deadlift",
}
_KIND = "|".join(sorted(KINDS, key=len, reverse=True))
KIND_RE = re.compile(rf"\b({_KIND})\b", re.IGNORECASE)
CARDIO = re.compile(
    r"treadmill|incline\s+\d|^\d+\s*min|\brun\b|\bjog\b|steps|cardio|shadow", re.IGNORECASE
)
INJURY = [
    (re.compile(r"glute sprain", re.IGNORECASE), "glute sprain"),
    (re.compile(r"biceps strain", re.IGNORECASE), "biceps strain"),
    (re.compile(r"tendon hurt", re.IGNORECASE), "knee tendon pain"),
    (re.compile(r"lower back tingling", re.IGNORECASE), "lower back"),
]
PHASES = [
    (re.compile(r"maintenance phase", re.IGNORECASE), "maintenance"),
    (re.compile(r"cut phase", re.IGNORECASE), "cut"),
]


@dataclass
class DiaryDay:
    """One session as written, before we know its exact date."""

    day: date | None
    kind: str
    exercises: list[Exercise] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    kcal: int | None = None
    sleep_h: float | None = None
    injuries: list[str] = field(default_factory=list)
    marked_prs: list[str] = field(default_factory=list)
    estimated_date: bool = False


@dataclass
class Diary:
    days: list[DiaryDay]
    body_weight: list[tuple[date, float]]
    phases: list[tuple[date, str]]
    skipped: list[str]


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_date(line: str, year: int) -> date | None:
    candidates = [(MONTHS[m[1].lower()], int(m[2])) for m in DATE_MD.finditer(line)]
    candidates += [(MONTHS[m[2].lower()], int(m[1])) for m in DATE_DM.finditer(line)]
    for month, day in candidates:  # "November 98.5kg" isn't a date: try the next reading
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None


def _reps(spec: str, n_sets: int) -> list[int]:
    """'8-7' over 2 sets -> [8, 7]; '6' over 3 sets -> [6, 6, 6]; '7.5' -> 7."""
    parts = [int(_num(p)) for p in re.split(r"\s*-\s*", spec.strip()) if p.strip()]
    if not parts:
        return []
    reps = parts + [parts[-1]] * (n_sets - len(parts))
    return [r for r in reps[: max(n_sets, 1)] if 0 < r <= 30]


def _load(chunk: str) -> tuple[float, str]:
    """Return (kg, text). kg is 0 when the load isn't a plain number of kg."""
    before = SET_RE.split(chunk)[0] if SET_RE.search(chunk) else chunk
    m = re.search(
        r"\bmax\b.*|\d+(?:[.,]\d+)?\s*plates?\b.*|\bpins?\b.*|\bstack\b.*", before, re.IGNORECASE
    )
    if m:  # keep just the load ("Max + 10kg", "5 Plates"), not the exercise name before it
        text = re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", m[0])).strip(" ,:")
        return 0.0, text
    m = KG.search(before) or KG.search(chunk)
    if m:
        return _num(m[1]), ""
    bare = re.search(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?=\s*$)", before.strip())
    return (_num(bare[1]), "") if bare else (0.0, "")


def parse_sets(text: str) -> list[SetEntry]:
    """Every '<load> <sets>x<reps>' group in a line, comma-separated."""
    out: list[SetEntry] = []
    rpe_all = RPE.findall(text)
    for chunk in re.split(
        r",(?![\d])|\+\s*superset", re.sub(r"\(.*?\)", "", text), flags=re.IGNORECASE
    ):
        if re.search(r"\bfail", chunk, re.IGNORECASE):
            continue  # a failed attempt isn't a set ("140kg 1x1 Fail", "205kg Attempt Fail")
        kg, load = _load(chunk)
        rpe_m = RPE.search(chunk)
        rpe = _rpe(rpe_m[1]) if rpe_m else None
        m = SET_RE.search(chunk)
        if m:
            n = int(m[1])
            if not 0 < n <= 10:
                continue
            reps = _reps(m[2], n)
        else:
            x = XREPS.search(chunk)
            reps = [int(x[1])] if x and 0 < int(x[1]) <= 30 else []
        out.extend(SetEntry(kg, r, rpe, False, load) for r in reps)
    if out and rpe_all and out[-1].rpe is None:
        out[-1] = SetEntry(out[-1].weight_kg, out[-1].reps, _rpe(rpe_all[-1]), False, out[-1].load)
    return out


def _rpe(s: str) -> float | None:
    v = _num(s)
    return v if 0 < v <= 10 else None  # "RPE 1000000" is a feeling, not a number


NAME_RE = re.compile(
    r"^([A-Za-z][A-Za-z ’'°&./-]*?)(?=\s+(?:\d|max\b|x\s*\d)|\s*[:,(]|$)", re.IGNORECASE
)
DEGREES = re.compile(r"^\d+°\s*")  # "45° Chest Supp Row" -> "Chest Supp Row"


def exercise_name(line: str) -> str | None:
    m = NAME_RE.match(re.sub(r"\bv\d\b", "", DEGREES.sub("", line.strip())))
    if not m:
        return None
    raw = re.sub(r"\b(top set|each)\b", "", m[1], flags=re.IGNORECASE).strip(" -")
    return normalize_name(raw) if raw else None


def is_header(line: str) -> bool:
    if SET_RE.search(line) or XREPS.search(line):
        return False
    s = line.strip().rstrip(":").strip()
    return bool(
        DATE_MD.search(s)
        or DATE_DM.search(s)
        or KIND_RE.fullmatch(s.split(":")[0].strip())
        or re.fullmatch(rf"({_KIND})\s*[A-Z0-9 ]*", s.split(":")[0].strip(), re.IGNORECASE)
    )


def parse_diary(text: str, start_year: int) -> Diary:
    """Parse one diary file. Year rolls over when the month goes backwards."""
    lines = [ln.replace("﻿", "").rstrip() for ln in text.splitlines()]
    days: list[DiaryDay] = []
    weights: list[tuple[date, float]] = []
    phases: list[tuple[date, str]] = []
    skipped: list[str] = []
    year, last_month = start_year, None
    cur: DiaryDay | None = None
    carry_name: str | None = None
    in_plan = False
    pending_phase: str | None = None

    def dated(line: str) -> date | None:
        nonlocal year, last_month
        d = parse_date(line, year)
        if d is None:
            return None
        if last_month and d.month < last_month - 6:
            year += 1
            d = d.replace(year=year)
        last_month = d.month
        return d

    for raw in lines:
        line = raw.strip()
        if not line:
            in_plan = False
            carry_name = None
            continue
        if re.match(r"^next\b", line, re.IGNORECASE):
            in_plan = True  # a plan for later, not a workout
            continue
        if in_plan:
            continue
        phase_hit = next((ph for rx, ph in PHASES if rx.search(line)), None)
        if phase_hit:
            pending_phase = phase_hit  # starts with the next session
            continue
        if line.lower().startswith(("week ", "note")) or re.match(
            r"^(new program|emphasis)", line, re.IGNORECASE
        ):
            if line.lower().startswith("week "):
                d = dated(line.split(":")[-1])
                bw = BODYWEIGHT.search(line)
                if d and bw:
                    weights.append((d, _num(bw[1])))
            continue
        if is_header(line):
            d = dated(line)
            kind_m = KIND_RE.search(line)
            kind = KINDS[kind_m[1].lower()] if kind_m else ""
            if re.search(r"\b(rest|sick)\b", line, re.IGNORECASE) and not kind:
                cur = None
                continue
            if cur and cur.day is None and d and not cur.exercises and not kind:
                cur.day = d  # "Upper: ... May 4th" style: the date line belongs to the open header
                continue
            if d is None and not kind:
                continue  # gym names etc.
            cur = DiaryDay(day=d, kind=kind)
            if pending_phase and d:
                phases.append((d, pending_phase))
                pending_phase = None
            k = KCAL.search(line)
            if k:
                cur.kcal = int(k[1])
            sl = re.search(
                r"(?:sub\s*)?(\d(?:\.\d)?)\s*h\b.*sleep|(\d(?:\.\d)?)h sleep", line, re.IGNORECASE
            )
            if sl:
                cur.sleep_h = _num(sl[1] or sl[2]) - (0.5 if "sub" in line.lower() else 0)
            note = re.search(r"\((.*?)\)", line)
            if note:
                cur.notes.append(note[1])
            days.append(cur)
            carry_name = None
            continue
        if cur is None:
            skipped.append(line)
            continue
        for rx, injury in INJURY:
            if rx.search(line):
                cur.injuries.append(injury)
        if CARDIO.search(line) and not SET_RE.search(line):
            cur.notes.append(line)
            continue
        name = exercise_name(line)
        sets = parse_sets(DEGREES.sub("", line))
        if line.endswith(":") and not sets and name:
            carry_name = name  # "Deadlift:" then the sets on the next lines
            continue
        if not sets and carry_name:
            continue
        if name is None or (carry_name and re.match(r"^(top set|\d)", line, re.IGNORECASE)):
            name = carry_name
        if name is None or not sets:
            skipped.append(line)
            continue
        if re.search(r"\bPR\b", line):
            cur.marked_prs.append(name)
        ex = next((e for e in cur.exercises if e.name == name), None)
        if ex:
            ex.sets.extend(sets)
        else:
            cur.exercises.append(Exercise(name, sets))
    return Diary([d for d in days if d.exercises], weights, phases, skipped)


def infer_kind(ex_names: list[str]) -> str:
    j = " ".join(ex_names)
    legs = any(w in j for w in ("squat", "leg ", "deadlift", "calf", "adductor"))
    push = any(w in j for w in ("bench", "press", "pec", "triceps", "lateral"))
    pull = any(w in j for w in ("pulldown", "row", "curl", "rear delt"))
    if legs and not (push or pull):
        return "lower"
    if legs:
        return "full body"
    if push and pull:
        return "upper"
    return "push" if push else "pull" if pull else "full body"


def assign_dates(days: list[DiaryDay], end: date) -> list[DiaryDay]:
    """Give undated sessions evenly spaced dates between their dated neighbours."""
    out = list(days)
    i = 0
    while i < len(out):
        if out[i].day is not None:
            i += 1
            continue
        j = i
        while j < len(out) and out[j].day is None:
            j += 1
        lo = out[i - 1].day if i > 0 else None
        hi = out[j].day if j < len(out) else end
        assert lo is not None, "the first session in a diary needs a date"
        gap = max((hi - lo).days, j - i + 1)
        step = gap / (j - i + 1)
        for k in range(i, j):
            out[k].day = lo + timedelta(days=max(1, round(step * (k - i + 1))))
            out[k].estimated_date = True
        i = j
    for d in out:
        if not d.kind:
            d.kind = infer_kind([e.name for e in d.exercises])
    # one session per (kind, day): merge accidental duplicates
    merged: dict[tuple[str, date], DiaryDay] = {}
    for d in out:
        assert d.day is not None
        key = (d.kind, d.day)
        if key in merged:
            merged[key].exercises.extend(d.exercises)
            merged[key].notes.extend(d.notes)
        else:
            merged[key] = d
    return sorted(merged.values(), key=lambda d: d.day or end)


def to_session(d: DiaryDay) -> Session:
    assert d.day is not None
    notes = list(d.notes) + (["date estimated"] if d.estimated_date else [])
    return Session(kind=d.kind, day=d.day, exercises=d.exercises, notes=notes)
