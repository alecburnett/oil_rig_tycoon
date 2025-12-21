from dataclasses import dataclass
from enum import Enum, auto
from datetime import date
import random
import calendar
from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import RigType, Region
else:
    # We'll import them locally to avoid circular imports if any, 
    # but models.py doesn't depend on contracts.py so it's fine.
    from .models import RigType, Region


# -----------------------------
# Helpers
# -----------------------------

def add_months(d: date, months: int) -> date:
    """Add months to a date, clamping day-of-month to last day where needed."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# -----------------------------
# Schema
# -----------------------------

class ContractType(Enum):
    EXPLORATION = auto()
    DEVELOPMENT = auto()
    WORKOVER = auto()


class RigClassRequired(Enum):
    JACKUP = auto()
    SEMI = auto()
    DRILLSHIP = auto()
    SEMI_OR_DRILLSHIP = auto()


class PositioningRequired(Enum):
    ANY = auto()
    MORED_OK = auto()
    DP_REQUIRED = auto()


def rig_matches_class(rig_type: RigType, req_class: RigClassRequired) -> bool:
    if req_class == RigClassRequired.JACKUP:
        return rig_type == RigType.JACKUP
    if req_class == RigClassRequired.SEMI:
        return rig_type == RigType.SEMI
    if req_class == RigClassRequired.DRILLSHIP:
        return rig_type == RigType.DRILLSHIP
    if req_class == RigClassRequired.SEMI_OR_DRILLSHIP:
        return rig_type in (RigType.SEMI, RigType.DRILLSHIP)
    return False


@dataclass(frozen=True)
class Tender:
    id: int
    spec: ContractSpec

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "spec": {
                "contract_type": self.spec.contract_type.name,
                "region": self.spec.region.value,
                "start_date": self.spec.start_date.isoformat(),
                "months": self.spec.months,
                "water_depth_m": self.spec.water_depth_m,
                "harsh": self.spec.harsh,
                "rig_type": self.spec.rig_type.name,
                "positioning_required": self.spec.positioning_required.name,
                "min_condition": self.spec.min_condition,
                "min_dayrate": self.spec.min_dayrate,
                "max_dayrate": self.spec.max_dayrate,
                "early_termination_penalty_k": self.spec.early_termination_penalty_k,
            }
        }

    @classmethod
    def from_dict(cls, d: dict) -> Tender:
        s = d["spec"]
        spec = TenderSpec(
            contract_type=ContractType[s["contract_type"]],
            region=Region(s["region"]),
            start_date=date.fromisoformat(s["start_date"]),
            months=s["months"],
            water_depth_m=s["water_depth_m"],
            harsh=s["harsh"],
            rig_type=RigClassRequired[s["rig_type"]],
            positioning_required=PositioningRequired[s["positioning_required"]],
            min_condition=s["min_condition"],
            min_dayrate=s["min_dayrate"],
            max_dayrate=s["max_dayrate"],
            early_termination_penalty_k=s["early_termination_penalty_k"]
        )
        return cls(id=d["id"], spec=spec)


@dataclass(frozen=True)
class TenderSpec:
    contract_type: ContractType
    region: Region
    start_date: date
    months: int
    water_depth_m: int
    harsh: bool
    rig_type: RigClassRequired
    positioning_required: PositioningRequired
    min_condition: int
    min_dayrate: int
    max_dayrate: int
    early_termination_penalty_k: int


# -----------------------------
# Generator
# -----------------------------

@dataclass
class ContractGenConfig:
    # How many tenders per region per tick (before demand factor + noise)
    base_tenders_per_region: float = 0.5
    noise_max: float = 2.6

    # Region harsh probability
    harsh_prob_by_region: dict[Region, float] = None  # set in __post_init__

    # Contract-type weights
    type_weights: dict[ContractType, float] = None  # set in __post_init__

    # Dayrate anchors ($k/day) at "mid-cycle"
    base_dayrate_k: dict[RigClassRequired, int] = None  # set in __post_init__
    harsh_mult: float = 1.15
    dp_mult: float = 1.20

    # Water depth distributions by contract type (min, mode, max) in meters
    water_depth_triangular_m: dict[ContractType, tuple[int, int, int]] = None  # set in __post_init__

    # Duration menus (months) by contract type
    duration_choices_months: dict[ContractType, tuple[int, ...]] = None  # set in __post_init__

    # Start date jitter (months after "as_of_date")
    start_in_months_choices: tuple[int, ...] = (0, 0, 1, 1, 2, 3)

    def __post_init__(self) -> None:
        if self.harsh_prob_by_region is None:
            self.harsh_prob_by_region = {
                Region.NORTH_SEA: 0.3,
                Region.GOM: 0,
            }
        if self.type_weights is None:
            self.type_weights = {
                ContractType.WORKOVER: 0.25,
                ContractType.DEVELOPMENT: 0.50,
                ContractType.EXPLORATION: 0.25,
            }
        if self.base_dayrate_k is None:
            self.base_dayrate_k = {
                RigClassRequired.JACKUP: 120,
                RigClassRequired.SEMI: 240,
                RigClassRequired.DRILLSHIP: 300,
                RigClassRequired.SEMI_OR_DRILLSHIP: 270,
            }
        if self.water_depth_triangular_m is None:
            self.water_depth_triangular_m = {
                ContractType.WORKOVER: (20, 60, 150),
                ContractType.DEVELOPMENT: (30, 150, 800),
                ContractType.EXPLORATION: (80, 400, 2500),
            }
        if self.duration_choices_months is None:
            self.duration_choices_months = {
                # short, punchy, frequent
                ContractType.WORKOVER: (1, 2, 3, 4),
                # the bread-and-butter
                ContractType.DEVELOPMENT: (6, 9, 12, 18, 24),
                # fewer, longer-ish, higher variance
                ContractType.EXPLORATION: (3, 6, 9, 12),
            }


class ContractGenerator:
    def __init__(self, rng: random.Random | None = None, cfg: ContractGenConfig | None = None):
        self.rng = rng or random.Random()
        self.cfg = cfg or ContractGenConfig()

    def _pick_weighted(self, weights: dict[Enum, float]):
        items = list(weights.items())
        total = sum(w for _, w in items)
        r = self.rng.random() * total
        acc = 0.0
        for item, w in items:
            acc += w
            if r <= acc:
                return item
        return items[-1][0]

    def _pick_harsh(self, region: Region) -> bool:
        p = self.cfg.harsh_prob_by_region.get(region, 0.10)
        return self.rng.random() < p

    def _water_depth(self, ctype: ContractType) -> int:
        a, b, c = self.cfg.water_depth_triangular_m[ctype]
        return int(self.rng.triangular(a, c, b))

    def _duration_months(self, ctype: ContractType, harsh: bool) -> int:
        months = self.rng.choice(self.cfg.duration_choices_months[ctype])
        # Harsh work tends to carry a bit more committed time/admin drag
        if harsh and ctype != ContractType.WORKOVER and self.rng.random() < 0.30:
            months += 3
        return months

    def _start_date(self, *, as_of_date: date) -> date:
        # Simple: most contracts start now or soon; occasional 2–3 month lead
        lead_months = self.rng.choice(self.cfg.start_in_months_choices)
        # Prefer starts on the 1st (easy for monthly ticks), with rare mid-month
        if self.rng.random() < 0.85:
            base = date(as_of_date.year, as_of_date.month, 1)
        else:
            base = as_of_date
        return add_months(base, lead_months)

    def _rig_class_and_positioning(
        self,
        *,
        water_depth_m: int,
        harsh: bool
    ) -> tuple[RigClassRequired, PositioningRequired]:
        # Rig class from water depth
        if water_depth_m <= 120:
            rig_class = RigClassRequired.JACKUP
        elif water_depth_m <= 500:
            rig_class = RigClassRequired.SEMI
        else:
            rig_class = RigClassRequired.SEMI_OR_DRILLSHIP if water_depth_m <= 1200 else RigClassRequired.DRILLSHIP

        # Positioning from depth + harsh
        if water_depth_m <= 120:
            positioning = PositioningRequired.ANY
        elif water_depth_m <= 500:
            dp_chance = 0.15 + (0.25 if harsh else 0.0)
            positioning = PositioningRequired.DP_REQUIRED if self.rng.random() < dp_chance else PositioningRequired.MORED_OK
        else:
            dp_chance = 0.65 + (0.20 if harsh else 0.0)
            positioning = PositioningRequired.DP_REQUIRED if self.rng.random() < dp_chance else PositioningRequired.MORED_OK

        # Keep it simple: no JACKUP + DP_REQUIRED
        if rig_class == RigClassRequired.JACKUP and positioning == PositioningRequired.DP_REQUIRED:
            positioning = PositioningRequired.ANY

        return rig_class, positioning

    def _dayrate_range_k(
        self,
        *,
        rig_class: RigClassRequired,
        positioning: PositioningRequired,
        harsh: bool,
        oil_factor: float,   # ~0.6 bust .. 1.4 boom
        contract_type: ContractType,
    ) -> tuple[int, int]:
        base = self.cfg.base_dayrate_k[rig_class]
        mult = oil_factor

        if harsh:
            mult *= self.cfg.harsh_mult
        if positioning == PositioningRequired.DP_REQUIRED:
            mult *= self.cfg.dp_mult

        # Exploration has a touch more variance/optionality
        if contract_type == ContractType.EXPLORATION:
            mult *= 1.05

        max_k = max(40, int(base * mult))
        floor_ratio = 0.70 if contract_type == ContractType.EXPLORATION else 0.75
        min_k = max(30, int(max_k * floor_ratio))
        if min_k >= max_k:
            min_k = max_k - 5

        return min_k, max_k

    def _early_termination_penalty_k(
        self,
        *,
        dayrate_k_max: int,
        duration_months: int,
        contract_type: ContractType,
        harsh: bool,
    ) -> int:
        """
        Penalty is a simple function of contract value:
          penalty ≈ penalty_months * 30 days * max_dayrate
        Longer + harsher + development => stiffer penalties.
        """
        # Months of penalty "coverage"
        if contract_type == ContractType.WORKOVER:
            penalty_months = 1
        elif contract_type == ContractType.EXPLORATION:
            penalty_months = 2
        else:  # DEVELOPMENT
            penalty_months = 3

        if harsh:
            penalty_months += 1

        # Cap penalty months relative to duration (avoid absurd penalties on 1–2 month workovers)
        penalty_months = min(penalty_months, max(1, duration_months))

        penalty_k = int(dayrate_k_max * 30 * penalty_months)
        # Add a small admin/legal floor so penalties exist even if dayrates are low
        penalty_k = max(penalty_k, 1500)  # $1.5m floor
        return penalty_k

    def generate_tick(
        self,
        *,
        regions: Iterable[Region],
        next_contract_id: int,
        as_of_date: date,
        oil_factor: float = 1.0,       # 0.6 bust .. 1.4 boom
        demand_factor: float = 1.0,    # 0.5 low demand .. 1.8 high demand
    ) -> tuple[list[Tender], int]:
        out: list[Tender] = []
        cid = next_contract_id

        regions_list = list(regions)
        
        # Target 0-3 contracts total per tick
        base_n = self.cfg.base_tenders_per_region * demand_factor * len(regions_list) # Scaled but we clamp
        # Actually user requested 0-3 total, let's just model that directly
        # Center around ~1.5 for normal demand
        val = 1.5 * demand_factor + self.rng.uniform(-1.2, 1.2)
        n = int(round(val))
        n = max(0, min(3, n))

        for _ in range(n):
            region = self.rng.choice(regions_list)
            ctype = self._pick_weighted(self.cfg.type_weights)
            harsh = self._pick_harsh(region)
            water_depth_m = self._water_depth(ctype)

            rig_class, positioning = self._rig_class_and_positioning(
                water_depth_m=water_depth_m,
                harsh=harsh,
            )

            duration_months = self._duration_months(ctype, harsh)
            start = self._start_date(as_of_date=as_of_date)

            dayrate_k_min, dayrate_k_max = self._dayrate_range_k(
                rig_class=rig_class,
                positioning=positioning,
                harsh=harsh,
                oil_factor=oil_factor,
                contract_type=ctype,
            )

            penalty_k = self._early_termination_penalty_k(
                dayrate_k_max=dayrate_k_max,
                duration_months=duration_months,
                contract_type=ctype,
                harsh=harsh,
            )

            # min_condition for tender: base on contract type
            if ctype == ContractType.EXPLORATION:
                min_condition = 75
            elif ctype == ContractType.DEVELOPMENT:
                min_condition = 65
            else:
                min_condition = 50

            out.append(
                Tender(
                    id=cid,
                    spec=TenderSpec(
                        contract_type=ctype,
                        region=region,
                        start_date=start,
                        months=duration_months,
                        water_depth_m=water_depth_m,
                        harsh=harsh,
                        rig_type=rig_class,
                        positioning_required=positioning,
                        min_condition=min_condition,
                        min_dayrate=dayrate_k_min,
                        max_dayrate=dayrate_k_max,
                        early_termination_penalty_k=penalty_k,
                    )
                )
            )
            cid += 1

        return out, cid

    def to_dict(self) -> dict:
        # We'll save the config but only the parts that are likely to change or matter
        return {
            "config": {
                "base_tenders_per_region": self.cfg.base_tenders_per_region,
                "noise_max": self.cfg.noise_max,
                # For brevity, let's assume default config for now unless user needs it saved.
                # If we want full fidelity, we'd serialize the whole cfg.
            }
        }

    @classmethod
    def from_dict(cls, d: dict, rng: random.Random) -> ContractGenerator:
        # For now, just restore default config with d['config'] overrides if any
        cfg = ContractGenConfig()
        if "config" in d:
            cfg.base_tenders_per_region = d["config"].get("base_tenders_per_region", cfg.base_tenders_per_region)
            cfg.noise_max = d["config"].get("noise_max", cfg.noise_max)
        return cls(rng=rng, cfg=cfg)


# -----------------------------
# Demo
# -----------------------------

def _fmt(c: Contract) -> str:
    return (
        f"#{c.id} {c.region:10} {c.contract_type.name:11} "
        f"start={c.start_date.isoformat()} dur={c.duration_months:2}m "
        f"wd={c.water_depth_m:4}m harsh={str(c.harsh_required):5} "
        f"{c.rig_class_required.name:16} {c.positioning_required.name:9} "
        f"dayrate={c.dayrate_k_min}-{c.dayrate_k_max}k "
        f"penalty=${c.early_termination_penalty_k/1000:.1f}m"
    )


if __name__ == "__main__":
    rng = random.Random(42)
    gen = ContractGenerator(rng=rng)

    regions = ["NORTH_SEA", "GOM", "BRAZIL"]
    next_id = 1
    today = date(2025, 12, 1)

    for tick, (oil_factor, demand_factor) in enumerate([(0.75, 0.8), (1.0, 1.0), (1.3, 1.4)], start=1):
        contracts, next_id = gen.generate_tick(
            regions=regions,
            next_contract_id=next_id,
            as_of_date=add_months(today, tick - 1),
            oil_factor=oil_factor,
            demand_factor=demand_factor,
        )
        print(f"\n=== TICK {tick} (oil_factor={oil_factor}, demand_factor={demand_factor}) ===")
        for c in contracts:
            print(_fmt(c))
