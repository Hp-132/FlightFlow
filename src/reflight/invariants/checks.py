"""Invariant checker (F9, section 6E). Each check returns
{"passed": bool, "violations": [...]}; `run_all_checks` runs I1-I6 and
returns the combined report used by both the API and the CLI/tests."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value

SQL_I1_OVERSELL = """
-- available must always equal capacity minus (a) seats consumed by the
-- original scenario's booking_segments (never mutated -- an abandoned leg
-- on a still-flying connection is left stuck rather than released; see
-- README Decisions) and (b) seats currently held/confirmed by sagas.
SELECT si.flight_id, si.cabin, si.capacity, si.available, si.sold_other,
       COALESCE(orig.original_count, 0) AS original_count,
       COALESCE(h.held_qty, 0) AS held_qty
FROM seat_inventory si
LEFT JOIN (
    SELECT flight_id, cabin, COUNT(*) AS original_count
    FROM booking_segments
    GROUP BY flight_id, cabin
) orig ON orig.flight_id = si.flight_id AND orig.cabin = si.cabin
LEFT JOIN (
    SELECT flight_id, cabin, SUM(qty) AS held_qty
    FROM seat_holds
    WHERE status IN ('HELD', 'CONFIRMED')
    GROUP BY flight_id, cabin
) h ON h.flight_id = si.flight_id AND h.cabin = si.cabin
WHERE si.available < 0
   OR si.available <> si.capacity - si.sold_other - COALESCE(orig.original_count, 0) - COALESCE(h.held_qty, 0)
"""

SQL_I2_LOST_OR_NONTERMINAL = """
SELECT b.id AS booking_id, b.status, s.id AS saga_id, s.state
FROM bookings b
LEFT JOIN sagas s ON s.booking_id = b.id AND s.run_id = :run_id
WHERE b.status <> 'ACTIVE'
  AND (s.id IS NULL OR s.state NOT IN
       ('COMPLETED', 'COMPENSATED', 'FAILED_NO_CAPACITY', 'NEEDS_MANUAL'))
"""

SQL_I3_MULTIPLE_CONFIRMED = """
SELECT s.booking_id, COUNT(DISTINCT sh.saga_id) AS confirmed_saga_count
FROM seat_holds sh
JOIN sagas s ON s.id = sh.saga_id
WHERE sh.status = 'CONFIRMED' AND s.run_id = :run_id
GROUP BY s.booking_id
HAVING COUNT(DISTINCT sh.saga_id) > 1
"""

SQL_I4_COMPENSATED_LEAKS = """
SELECT s.id AS saga_id,
       COUNT(sh.id) FILTER (WHERE sh.status IN ('HELD', 'CONFIRMED')) AS leaked_holds,
       COUNT(t.id) FILTER (WHERE t.status = 'ISSUED') AS active_tickets
FROM sagas s
LEFT JOIN seat_holds sh ON sh.saga_id = s.id
LEFT JOIN partners.tickets t ON t.saga_id = s.id::text
WHERE s.state = 'COMPENSATED' AND s.run_id = :run_id
GROUP BY s.id
HAVING COUNT(sh.id) FILTER (WHERE sh.status IN ('HELD', 'CONFIRMED')) > 0
    OR COUNT(t.id) FILTER (WHERE t.status = 'ISSUED') > 0
"""

SQL_I5_COMPLETED_MISSING = """
SELECT s.id AS saga_id,
       COUNT(sh.id) FILTER (WHERE sh.status = 'CONFIRMED') AS confirmed_holds,
       COUNT(t.id) FILTER (WHERE t.status = 'ISSUED') AS issued_tickets
FROM sagas s
LEFT JOIN seat_holds sh ON sh.saga_id = s.id
LEFT JOIN partners.tickets t ON t.saga_id = s.id::text
WHERE s.state = 'COMPLETED' AND s.run_id = :run_id
GROUP BY s.id
HAVING COUNT(sh.id) FILTER (WHERE sh.status = 'CONFIRMED') = 0
    OR COUNT(t.id) FILTER (WHERE t.status = 'ISSUED') = 0
"""

SQL_I6_UNPUBLISHED_OUTBOX = """
SELECT id, routing_key, created_at
FROM outbox
WHERE published_at IS NULL
"""


def _rows_to_dicts(result) -> list[dict[str, Any]]:
    return [{k: _jsonable(v) for k, v in row._mapping.items()} for row in result]


def check_i1_no_oversell(db: Session) -> dict[str, Any]:
    violations = _rows_to_dicts(db.execute(text(SQL_I1_OVERSELL)))
    return {"passed": len(violations) == 0, "violations": violations}


def check_i2_no_lost_bookings(db: Session, run_id: str) -> dict[str, Any]:
    violations = _rows_to_dicts(db.execute(text(SQL_I2_LOST_OR_NONTERMINAL), {"run_id": run_id}))
    return {"passed": len(violations) == 0, "violations": violations}


def check_i3_single_confirmed_itinerary(db: Session, run_id: str) -> dict[str, Any]:
    violations = _rows_to_dicts(db.execute(text(SQL_I3_MULTIPLE_CONFIRMED), {"run_id": run_id}))
    return {"passed": len(violations) == 0, "violations": violations}


def check_i4_compensated_no_leaks(db: Session, run_id: str) -> dict[str, Any]:
    violations = _rows_to_dicts(db.execute(text(SQL_I4_COMPENSATED_LEAKS), {"run_id": run_id}))
    return {"passed": len(violations) == 0, "violations": violations}


def check_i5_completed_has_holds_and_ticket(db: Session, run_id: str) -> dict[str, Any]:
    violations = _rows_to_dicts(db.execute(text(SQL_I5_COMPLETED_MISSING), {"run_id": run_id}))
    return {"passed": len(violations) == 0, "violations": violations}


def check_i6_outbox_fully_published(db: Session) -> dict[str, Any]:
    violations = _rows_to_dicts(db.execute(text(SQL_I6_UNPUBLISHED_OUTBOX)))
    return {"passed": len(violations) == 0, "violations": violations}


def run_all_checks(db: Session, run_id: str) -> dict[str, Any]:
    checks = {
        "I1_no_oversell": check_i1_no_oversell(db),
        "I2_no_lost_bookings": check_i2_no_lost_bookings(db, run_id),
        "I3_single_confirmed_itinerary": check_i3_single_confirmed_itinerary(db, run_id),
        "I4_compensated_no_leaks": check_i4_compensated_no_leaks(db, run_id),
        "I5_completed_has_holds_and_ticket": check_i5_completed_has_holds_and_ticket(db, run_id),
        "I6_outbox_fully_published": check_i6_outbox_fully_published(db),
    }
    overall_passed = all(c["passed"] for c in checks.values())
    total_violations = sum(len(c["violations"]) for c in checks.values())
    return {"passed": overall_passed, "total_violations": total_violations, "checks": checks}
