"""Deterministic temporal grounding — *kala-bodha* (काल-बोध, awareness of time).

Conversations speak in relative time: "I went to the support group
*yesterday*", "we moved *last month*", "the concert was *two weekends ago*".
A reader model that sees only the session date must do calendar arithmetic
to answer "when did she go?", and small local models get it wrong often.
Leading memory systems resolve these phrases with an LLM at write time; this
module does the common cases with zero tokens, zero dependencies and no
network:

* ``find_mentions(text, anchor)`` → resolved :class:`TimeMention` spans.
* ``annotate(text, anchor)`` → the text with absolute dates inserted after
  each resolved phrase (``yesterday [2023-05-07]``). Raw episodes are never
  rewritten; annotation happens when context is rendered.
* ``query_window(query, now)`` → the date window a question refers to
  ("what did I do last weekend?"), used as a retrieval prior.

Precision over recall: ambiguous forms ("on Friday" with no tense cue, bare
month names, "recently") are left alone rather than guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import List, Optional, Tuple

_NUM_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "a couple of": 2, "couple of": 2, "a couple": 2,
}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday"]
_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]
_MONTH_IDX = {m: i + 1 for i, m in enumerate(_MONTHS)}
_MONTH_IDX.update({m[:3]: i + 1 for i, m in enumerate(_MONTHS)})
_MONTH_IDX["sept"] = 9
_SEASONS = {"spring": (3, 5), "summer": (6, 8), "fall": (9, 11), "autumn": (9, 11),
            "winter": (12, 2)}


@dataclass(frozen=True)
class TimeMention:
    start: int            # character span in the source text
    end: int
    phrase: str
    first: date           # resolved inclusive date range
    last: date
    granularity: str      # day | weekend | week | month | season | year

    def label(self) -> str:
        """Compact absolute rendering used in annotations."""
        if self.granularity == "day":
            return self.first.isoformat()
        if self.granularity == "month":
            return self.first.strftime("%Y-%m")
        if self.granularity == "year":
            return str(self.first.year)
        return f"{self.first.isoformat()}..{self.last.isoformat()}"


def parse_anchor(value) -> Optional[date]:
    """Accept an ISO string / datetime / date; return a date or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", str(value))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _month_add(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def _month_range(first_of_month: date) -> Tuple[date, date]:
    nxt = _month_add(first_of_month, 1)
    return first_of_month, nxt - timedelta(days=1)


def _week_range(d: date) -> Tuple[date, date]:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def _num(token: str) -> Optional[int]:
    token = token.lower().strip()
    if token.isdigit():
        n = int(token)
        return n if 0 < n <= 400 else None
    return _NUM_WORDS.get(token)


_NUM_RE = r"(\d{1,3}|a couple of|couple of|a couple|an|a|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_WD_RE = "(" + "|".join(_WEEKDAYS) + ")"
_SEASON_RE = "(spring|summer|fall|autumn|winter)"

# Ordered: longer / more specific patterns first. Each entry is
# (compiled regex, resolver(match, anchor) -> (first, last, granularity) | None)
_RULES: List[tuple] = []


def _rule(pattern: str):
    def deco(fn):
        _RULES.append((re.compile(pattern, re.IGNORECASE), fn))
        return fn
    return deco


@_rule(r"\bthe day before yesterday\b")
def _dby(m, a):
    d = a - timedelta(days=2)
    return d, d, "day"


@_rule(r"\bthe day after tomorrow\b")
def _dat(m, a):
    d = a + timedelta(days=2)
    return d, d, "day"


@_rule(r"\b(yesterday|last night)\b")
def _yesterday(m, a):
    d = a - timedelta(days=1)
    return d, d, "day"


@_rule(r"\b(today|tonight|this morning|this afternoon|this evening|earlier today)\b")
def _today(m, a):
    return a, a, "day"


@_rule(r"\btomorrow\b")
def _tomorrow(m, a):
    d = a + timedelta(days=1)
    return d, d, "day"


@_rule(r"\b" + _NUM_RE + r"\s+(day|week|weekend|month|year)s?\s+ago\b")
def _ago(m, a):
    n = _num(m.group(1))
    unit = m.group(2).lower()
    if n is None:
        return None
    if unit == "day":
        d = a - timedelta(days=n)
        return d, d, "day"
    if unit == "week":
        return (*_week_range(a - timedelta(weeks=n)), "week")
    if unit == "weekend":
        sat = a - timedelta(days=(a.weekday() - 5) % 7 or 7)
        sat -= timedelta(weeks=n - 1)
        return sat, sat + timedelta(days=1), "weekend"
    if unit == "month":
        return (*_month_range(_month_add(a.replace(day=1), -n)), "month")
    y = a.year - n
    return date(y, 1, 1), date(y, 12, 31), "year"


@_rule(r"\bin\s+" + _NUM_RE + r"\s+(day|week|month|year)s?\b(?!\s+ago)")
def _in_n(m, a):
    n = _num(m.group(1))
    unit = m.group(2).lower()
    if n is None:
        return None
    if unit == "day":
        d = a + timedelta(days=n)
        return d, d, "day"
    if unit == "week":
        return (*_week_range(a + timedelta(weeks=n)), "week")
    if unit == "month":
        return (*_month_range(_month_add(a.replace(day=1), n)), "month")
    y = a.year + n
    return date(y, 1, 1), date(y, 12, 31), "year"


@_rule(r"\b(last|this past|this coming|this|next)\s+weekend\b")
def _weekend(m, a):
    which = m.group(1).lower()
    if which in ("last", "this past"):
        # most recent Saturday strictly before the anchor's own weekend
        sat = a - timedelta(days=(a.weekday() - 5) % 7 or 7)
        if a.weekday() >= 5:
            sat = a - timedelta(days=a.weekday() - 5) - timedelta(days=7)
        return sat, sat + timedelta(days=1), "weekend"
    sat = a + timedelta(days=(5 - a.weekday()) % 7)
    if a.weekday() == 6:
        sat = a - timedelta(days=1)
    if which == "next":
        sat += timedelta(days=7) if a.weekday() < 5 else timedelta(days=7)
    return sat, sat + timedelta(days=1), "weekend"


@_rule(r"\b(last|this past|this|next)\s+" + _WD_RE + r"\b")
def _weekday(m, a):
    which, wd = m.group(1).lower(), _WEEKDAYS.index(m.group(2).lower())
    if which in ("last", "this past"):
        delta = (a.weekday() - wd) % 7 or 7
        d = a - timedelta(days=delta)
        return d, d, "day"
    if which == "next":
        delta = (wd - a.weekday()) % 7 or 7
        d = a + timedelta(days=delta)
        return d, d, "day"
    # "this <weekday>": the one inside the anchor's Mon..Sun week
    d = a - timedelta(days=a.weekday()) + timedelta(days=wd)
    return d, d, "day"


@_rule(r"\b(last|this past|this|next)\s+(week|month|year)\b")
def _period(m, a):
    which, unit = m.group(1).lower(), m.group(2).lower()
    step = -1 if which in ("last", "this past") else (1 if which == "next" else 0)
    if unit == "week":
        return (*_week_range(a + timedelta(weeks=step)), "week")
    if unit == "month":
        return (*_month_range(_month_add(a.replace(day=1), step)), "month")
    y = a.year + step
    return date(y, 1, 1), date(y, 12, 31), "year"


@_rule(r"\bearlier this (week|month|year)\b")
def _earlier_this(m, a):
    unit = m.group(1).lower()
    if unit == "week":
        first, _ = _week_range(a)
        return first, a, "week"
    if unit == "month":
        return a.replace(day=1), a, "month"
    return date(a.year, 1, 1), a, "year"


@_rule(r"\b(last|this past|this|next)\s+" + _SEASON_RE + r"\b")
def _season(m, a):
    which, season = m.group(1).lower(), m.group(2).lower()
    s0, s1 = _SEASONS[season]

    def season_of_year(y: int) -> Tuple[date, date]:
        if season == "winter":  # Dec(y) .. Feb(y+1)
            first = date(y, 12, 1)
            return first, _month_range(date(y + 1, 2, 1))[1]
        return date(y, s0, 1), _month_range(date(y, s1, 1))[1]

    # candidate seasons around the anchor, pick relative to it
    cands = [season_of_year(y) for y in (a.year - 2, a.year - 1, a.year, a.year + 1)]
    if which in ("last", "this past"):
        past = [c for c in cands if c[1] < a]
        if not past:
            return None
        first, last = past[-1]
    elif which == "next":
        fut = [c for c in cands if c[0] > a]
        if not fut:
            return None
        first, last = fut[0]
    else:  # "this summer": containing or nearest upcoming in the same year
        cur = [c for c in cands if c[0] <= a <= c[1]]
        if cur:
            first, last = cur[0]
        else:
            same = [c for c in cands if c[0].year == a.year]
            if not same:
                return None
            first, last = same[0]
    return first, last, "season"


# One cheap scan that every rule's match must also satisfy; texts without any
# trigger word skip the per-rule scans entirely (most turns, at read time).
_UNITS = (r"(?:night|weekend|week|month|year|morning|afternoon|evening|spring|summer|fall|"
          r"autumn|winter|monday|tuesday|wednesday|thursday|friday|saturday|sunday)")
_TRIGGER = re.compile(
    r"\b(?:yesterday|today|tonight|tomorrow|ago|earlier this|"
    r"(?:last|next|this|this past|this coming)\s+" + _UNITS + r"|"
    r"in\s+(?:\d{1,3}|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"a couple of|couple of)\s+(?:day|week|month|year)s?)\b",
    re.IGNORECASE)


def find_mentions(text: str, anchor) -> List[TimeMention]:
    """Resolve relative temporal phrases in ``text`` against ``anchor``."""
    a = parse_anchor(anchor)
    if a is None or not text:
        return []
    return list(_find_cached(text, a))


@lru_cache(maxsize=16384)
def _find_cached(text: str, a: date) -> Tuple[TimeMention, ...]:
    if not _TRIGGER.search(text):
        return ()
    taken: List[Tuple[int, int]] = []
    out: List[TimeMention] = []
    for regex, fn in _RULES:
        for m in regex.finditer(text):
            s, e = m.span()
            if any(s < te and e > ts for ts, te in taken):
                continue
            try:
                res = fn(m, a)
            except (ValueError, OverflowError):
                res = None
            if not res:
                continue
            first, last, gran = res
            taken.append((s, e))
            out.append(TimeMention(s, e, m.group(0), first, last, gran))
    out.sort(key=lambda t: t.start)
    return tuple(out)


def annotate(text: str, anchor, max_mentions: int = 6) -> str:
    """Insert absolute dates after resolved phrases: ``yesterday [2023-05-07]``."""
    mentions = find_mentions(text, anchor)[:max_mentions]
    if not mentions:
        return text
    parts, cursor = [], 0
    for mt in mentions:
        parts.append(text[cursor:mt.end])
        parts.append(f" [{mt.label()}]")
        cursor = mt.end
    parts.append(text[cursor:])
    return "".join(parts)


# ---------------------------------------------------------- query windows
_EXPLICIT_MONTH_YEAR = re.compile(
    r"\b(" + "|".join(_MONTHS) + r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s+(\d{4})\b",
    re.IGNORECASE)
_EXPLICIT_DAY = re.compile(
    r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b|\b(\d{1,2})(?:st|nd|rd|th)?\s+("
    + "|".join(_MONTHS) + r")\s*,?\s*(\d{4})\b|\b(" + "|".join(_MONTHS)
    + r")\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})\b", re.IGNORECASE)
_PAST_MONTH = re.compile(r"\b(?:in|during|since|back in)\s+(" + "|".join(_MONTHS) + r")\b(?!\s+\d)",
                         re.IGNORECASE)
_PAST_N = re.compile(r"\b(?:in the |over the |during the )?(?:past|last)\s+" + _NUM_RE
                     + r"\s+(day|week|month|year)s\b", re.IGNORECASE)


def query_window(query: str, now) -> Optional[Tuple[date, date]]:
    """Date window a question refers to, or None when it names no period.

    Handles relative phrases (via :func:`find_mentions`), "in the past N
    weeks", explicit dates / "Month YYYY", and "in March" (most recent March
    on or before ``now``)."""
    a = parse_anchor(now)
    if not query:
        return None
    m = _EXPLICIT_DAY.search(query)
    if m:
        try:
            if m.group(1):
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            elif m.group(4):
                d = date(int(m.group(6)), _MONTH_IDX[m.group(5).lower()], int(m.group(4)))
            else:
                d = date(int(m.group(9)), _MONTH_IDX[m.group(7).lower()], int(m.group(8)))
            return d, d
        except (ValueError, KeyError):
            pass
    m = _EXPLICIT_MONTH_YEAR.search(query)
    if m:
        mon = _MONTH_IDX.get(m.group(1).lower().rstrip("."))
        if mon:
            return _month_range(date(int(m.group(2)), mon, 1))
    if a is None:
        return None
    m = _PAST_N.search(query)
    if m:
        n = _num(m.group(1))
        unit = m.group(2).lower()
        if n:
            days = {"day": 1, "week": 7, "month": 31, "year": 366}[unit] * n
            return a - timedelta(days=days), a
    mentions = find_mentions(query, a)
    if mentions:
        return mentions[0].first, mentions[0].last
    m = _PAST_MONTH.search(query)
    if m:
        mon = _MONTH_IDX[m.group(1).lower()]
        y = a.year if mon <= a.month else a.year - 1
        return _month_range(date(y, mon, 1))
    return None
