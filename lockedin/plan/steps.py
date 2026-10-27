"""How much a lift moves up, and how much comes off after weeks away from it."""

import math

# Smallest jump the equipment allows, kg; per dumbbell for dumbbells. Anything else (a dip belt, plates) is 2.5.
INCREMENT_KG = {"barbell": 2.5, "dumbbell": 2.0, "machine": 5.0, "cable": 2.5}
OTHER_INCREMENT_KG = 2.5
# A step up is ~5% of the load on that grid, at least one increment, never over 10% unless one increment already is
# (ACSM 2009 progression model: 2–10%).
STEP_SHARE = 0.05
MAX_STEP_SHARE = 0.10
# Strength holds for ~3 weeks off a lift, then fades (Mujika & Padilla 2000; McMaster et al. 2013).
FRESH_DAYS = 21
LONG_GAP_DAYS = 56
GAP_CUTS = ((LONG_GAP_DAYS, 0.10), (None, 0.20))  # up to 8 weeks away: −10%; longer: −20%
BACK_FROM_OFF_DAYS = 14  # a lift's region was restricted and ended within this many days: ease in
BACK_FROM_OFF_CUT = 0.10
EPS = 1e-9


def _grid(equipment: str, dumbbell_logging: str) -> tuple[float, int]:
    """(increment per weight, weights per logged number): a dumbbell pair logged together moves two dumbbells."""
    pair = 2 if equipment == "dumbbell" and dumbbell_logging == "pair" else 1
    return INCREMENT_KG.get(equipment, OTHER_INCREMENT_KG), pair


def step_up(kg: float, equipment: str, dumbbell_logging: str) -> float:
    inc, pair = _grid(equipment, dumbbell_logging)
    load = kg / pair
    n = max(1, min(math.floor(load * STEP_SHARE / inc + 0.5 + EPS), math.floor(load * MAX_STEP_SHARE / inc + EPS)))
    return n * inc * pair


def gap_cut(days_away: int | None) -> float:
    """Share to take off a lift last logged `days_away` days ago (0 when it's fresh or never done)."""
    if days_away is None or days_away <= FRESH_DAYS:
        return 0.0
    return next(cut for upto, cut in GAP_CUTS if upto is None or days_away <= upto)


def eased(kg: float, equipment: str, dumbbell_logging: str, cut: float) -> float:
    """`kg` less `cut`, rounded down to a weight the equipment has (never to nothing)."""
    inc, pair = _grid(equipment, dumbbell_logging)
    load = kg / pair
    lighter = math.floor(load * (1 - cut) / inc + EPS) * inc
    return round((lighter if lighter > 0 else load) * pair, 2)
