from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RigType(str, Enum):
    JACKUP = "jackup"
    SEMI = "semisub"
    DRILLER = "drillship"


class RigState(str, Enum):
    ACTIVE = "active"
    WARM = "warm"
    COLD = "cold"
    SCRAP = "scrap"


class Region(str, Enum):
    NORTH_SEA = "north_sea"
    GOM = "gom"  # Gulf of Mexico (mild)


@dataclass(frozen=True)
class ContractSpec:
    region: Region
    months: int
    rig_type: RigType
    min_spec: int          # 0-100
    harsh: bool
    # operator willingness to pay (used to cap bids)
    max_dayrate: int       # $k/day


@dataclass
class Contract:
    id: int
    spec: ContractSpec
    awarded_to: Optional[str] = None
    rig_id: Optional[int] = None
    dayrate: Optional[int] = None  # $k/day


@dataclass
class Rig:
    id: int
    rig_type: RigType
    age_years: int
    spec: int               # 0-100
    region: Region
    state: RigState = RigState.WARM
    on_contract_months_left: int = 0
    contract_dayrate: int = 0      # $k/day

    @property
    def is_available(self) -> bool:
        return self.state in (RigState.WARM, RigState.COLD) and self.on_contract_months_left == 0

    def opex_per_day_k(self) -> int:
        """
        Very rough. You’ll tune this.
        """
        base = 55 if self.rig_type == RigType.JACKUP else 95
        age_penalty = max(0, self.age_years - 10) * 2
        spec_penalty = max(0, (70 - self.spec)) // 5
        return base + age_penalty + spec_penalty

    def stacking_cost_per_month_k(self) -> int:
        if self.state == RigState.WARM:
            return 450  # $k/month
        if self.state == RigState.COLD:
            return 180
        return 0


@dataclass
class Company:
    name: str
    cash_musd: float
    rigs: list[Rig] = field(default_factory=list)
    reputation: float = 0.5     # 0-1
    debt_musd: float = 0.0