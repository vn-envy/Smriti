"""As-of queries over the tri-temporal model — the E1A correctness milestone.

Two independent time axes, queryable together:

  * world:  what was TRUE at time W          (valid_from / invalid_at)
  * known:  what this store BELIEVED at K    (recorded_at / withdrawn_at)

`facts_asof(store, world=..., known=...)` answers all four combinations:
  neither     -> currently valid, currently believed (like core valid-only)
  world only  -> what was true then, per current belief
  known only  -> what the store believed then (late corrections invisible)
  both        -> full reconstruction: "on K, what did we think was true at W?"
"""
from __future__ import annotations

from typing import List, Optional

from smriti.types import Fact

_COLS = ("id, statement, subject, predicate, object, kind, event_date, "
         "ingested_at, valid_from, invalid_at, superseded_by, episode_id, session_id")


def _row_to_fact(row) -> Fact:
    return Fact(id=row[0], statement=row[1], subject=row[2], predicate=row[3],
                object=row[4], kind=row[5], event_date=row[6], ingested_at=row[7],
                valid_from=row[8], invalid_at=row[9], superseded_by=row[10],
                episode_id=row[11], session_id=row[12])


def facts_asof(store, world: Optional[str] = None, known: Optional[str] = None,
               subject: Optional[str] = None,
               include_observations: bool = False) -> List[Fact]:
    conds, args = [], []
    if not include_observations:
        conds.append("kind != 'observation'")
    if subject is not None:
        conds.append("subject = ?")
        args.append(subject.lower().strip())

    if known is not None:
        # The fact itself must have been recorded by K. For a known-only query,
        # withdrawal decides whether it was still believed. With a world-time
        # query, withdrawal instead gates whether invalid_at was known at K;
        # filtering it here would incorrectly erase true earlier history.
        conds.append("(recorded_at IS NOT NULL AND recorded_at <= ?)")
        args.append(known)
        if world is None:
            conds.append("(withdrawn_at IS NULL OR withdrawn_at > ?)")
            args.append(known)
    else:
        conds.append("withdrawn_at IS NULL OR withdrawn_at IS NOT NULL")  # no-op

    if world is not None:
        # true at W (per the belief snapshot selected above)
        conds.append("(valid_from IS NULL OR valid_from <= ?)")
        args.append(world)
        if known is not None:
            # within the belief snapshot, a fact was 'still true at W' unless
            # that belief ALSO recorded an invalidation with world time <= W
            # AND that invalidation was already known at K (withdrawn side
            # handled above; invalid_at is world time and only meaningful if
            # the successor was known — approximated by withdrawn_at <= K).
            conds.append("""NOT EXISTS (
                SELECT 1 FROM fact_validity_history h
                 WHERE h.fact_id=facts.id AND h.known_at <= ?
                   AND h.revision_id=(
                       SELECT h2.revision_id
                         FROM fact_validity_history h2
                        WHERE h2.fact_id=facts.id AND h2.known_at <= ?
                        ORDER BY h2.known_at DESC, h2.revision_id DESC LIMIT 1)
                   AND h.invalid_at IS NOT NULL AND h.invalid_at <= ?)""")
            args.extend([known, known, world])
        else:
            conds.append("(invalid_at IS NULL OR invalid_at > ?)")
            args.append(world)
    elif known is None:
        conds.append("invalid_at IS NULL")   # default: current world truth

    sql = f"SELECT {_COLS} FROM facts WHERE " + " AND ".join(f"({c})" for c in conds)
    facts = [_row_to_fact(r) for r in store.db.execute(sql, args).fetchall()]
    if world is not None and known is not None:
        # The row columns are the mutable current projection. Return the same
        # historical interval state used to select the row, so callers do not
        # receive (for example) a July answer carrying an August correction.
        for fact in facts:
            state = store.db.execute(
                """SELECT valid_from, invalid_at, superseded_by
                     FROM fact_validity_history
                    WHERE fact_id=? AND known_at <= ?
                    ORDER BY known_at DESC, revision_id DESC LIMIT 1""",
                (fact.id, known)).fetchone()
            if state:
                fact.valid_from, fact.invalid_at, fact.superseded_by = state
    return facts
