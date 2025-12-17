from __future__ import annotations
from dataclasses import dataclass
from .models import Company, Contract, RigState


@dataclass(frozen=True)
class AIPersonality:
    aggressiveness: float  # 0-1 (higher bids lower)
    desperation: float     # 0-1 (willing to bid below cost)
    quality_bias: float    # 0-1 (prefers high spec work)


def estimate_break_even_dayrate_k(company: Company, rig_id: int, current_year: int) -> int:
    rig = next(r for r in company.rigs if r.id == rig_id)
    opex = rig.opex_per_day_k(current_year)
    # rough overhead + G&A
    overhead = 12
    # older rigs often need more maintenance
    age = max(0, current_year - rig.build_year)
    maint = max(0, age - 12)
    return opex + overhead + maint


def choose_bid(company: Company, personality: AIPersonality, tender: Tender) -> tuple[int, int] | None:
    """
    Returns (rig_id, dayrate_k) or None to not bid.
    """
    # use tender start date as the "year" for bidding decisions
    current_year = tender.spec.start_date.year

    # pick best available rig for spec/region/type
    candidates = []
    for rig in company.rigs:
        if not rig.is_available:
            continue
        if rig.state == RigState.SCRAP:
            continue
        if rig.rig_type != tender.spec.rig_type:
            continue
        if rig.region != tender.spec.region:
            continue
        if rig.condition < tender.spec.min_condition:
            continue
        candidates.append(rig)

    if not candidates:
        return None

    # prefer closer-to-required condition unless quality_bias high
    candidates.sort(key=lambda r: (abs(r.condition - tender.spec.min_condition) * (1 - personality.quality_bias), -r.condition))
    rig = candidates[0]

    breakeven = estimate_break_even_dayrate_k(company, rig.id, current_year)

    # AI pricing: start from max willingness and shade down
    # aggressiveness => larger discount
    discount = int((0.05 + 0.35 * personality.aggressiveness) * tender.spec.max_dayrate)
    bid = tender.spec.max_dayrate - discount

    # if cash is low and rigs idle, can bid close to break-even or below (desperation)
    if company.cash_musd < 25:
        bid = min(bid, breakeven + 8)

    if personality.desperation > 0.6 and company.cash_musd < 15:
        bid = min(bid, breakeven - int(5 * personality.desperation))

    # never bid above max
    bid = min(bid, tender.spec.max_dayrate)

    # optionally skip bad economics
    if bid < breakeven - 10 and personality.desperation < 0.5:
        return None

    return (rig.id, max(1, bid))