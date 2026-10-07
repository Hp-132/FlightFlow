"""Priority scoring (F5): unaccompanied minors, elite tier, tight
connections first. Shared by the planner (sort order) and the worker
(RabbitMQ message priority)."""

from reflight.core.constants import TIER_GOLD, TIER_SILVER

SCORE_UNACCOMPANIED_MINOR = 100
SCORE_GOLD = 50
SCORE_SILVER = 20
SCORE_TIGHT_CONNECTION_BONUS = 30


def compute_priority(*, tier: str, is_unaccompanied_minor: bool, has_connection: bool) -> int:
    score = 0
    if is_unaccompanied_minor:
        score += SCORE_UNACCOMPANIED_MINOR
    elif tier == TIER_GOLD:
        score += SCORE_GOLD
    elif tier == TIER_SILVER:
        score += SCORE_SILVER
    if has_connection:
        score += SCORE_TIGHT_CONNECTION_BONUS
    return score


def to_rabbitmq_priority(score: int, max_priority: int = 9) -> int:
    """Map an unbounded priority score onto RabbitMQ's 0-max_priority range."""
    return max(0, min(max_priority, score // 15))
