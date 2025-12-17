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

    def to_json(self) -> str:
        return self.value


@dataclass(frozen=True)
class ContractSpec:
    region: Region
    months: int
    rig_type: RigType
    min_condition: int          # 0-100
    harsh: bool
    # operator willingness to pay (used to cap bids)
    max_dayrate: int       # $k/day

    def to_dict(self) -> dict:
        return {
            "region": self.region.value,
            "months": self.months,
            "rig_type": self.rig_type.value,
            "min_condition": self.min_condition,
            "harsh": self.harsh,
            "max_dayrate": self.max_dayrate,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ContractSpec:
        return cls(
            region=Region(d["region"]),
            months=d["months"],
            rig_type=RigType(d["rig_type"]),
            min_condition=d["min_condition"],
            harsh=d["harsh"],
            max_dayrate=d["max_dayrate"],
        )


@dataclass
class Contract:
    id: int
    spec: ContractSpec
    awarded_to: Optional[str] = None
    rig_id: Optional[int] = None
    dayrate: Optional[int] = None  # $k/day

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "spec": self.spec.to_dict(),
            "awarded_to": self.awarded_to,
            "rig_id": self.rig_id,
            "dayrate": self.dayrate,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Contract:
        return cls(
            id=d["id"],
            spec=ContractSpec.from_dict(d["spec"]),
            awarded_to=d.get("awarded_to"),
            rig_id=d.get("rig_id"),
            dayrate=d.get("dayrate"),
        )


@dataclass
class Rig:
    id: int
    rig_type: RigType
    build_year: int
    condition: int               # 0-100
    region: Region
    state: RigState = RigState.WARM
    on_contract_months_left: int = 0
    contract_dayrate: int = 0      # $k/day
    contract_id: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rig_type": self.rig_type.value,
            "build_year": self.build_year,
            "condition": self.condition,
            "region": self.region.value,
            "state": self.state.value,
            "on_contract_months_left": self.on_contract_months_left,
            "contract_dayrate": self.contract_dayrate,
            "contract_id": self.contract_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Rig:
        return cls(
            id=d["id"],
            rig_type=RigType(d["rig_type"]),
            build_year=d["build_year"],
            condition=d["condition"],
            region=Region(d["region"]),
            state=RigState(d["state"]),
            on_contract_months_left=d["on_contract_months_left"],
            contract_dayrate=d["contract_dayrate"],
            contract_id=d.get("contract_id"),
        )

    @property
    def is_available(self) -> bool:
        return self.state in (RigState.WARM, RigState.COLD) and self.on_contract_months_left == 0

    def opex_per_day_k(self, current_year: int) -> int:
        """
        Very rough. You’ll tune this.
        """
        base = 55 if self.rig_type == RigType.JACKUP else 95
        age_years = max(0, current_year - self.build_year)
        age_penalty = max(0, age_years - 10) * 2
        condition_penalty = max(0, (70 - self.condition)) // 5
        return base + age_penalty + condition_penalty

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

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "cash_musd": self.cash_musd,
            "reputation": self.reputation,
            "debt_musd": self.debt_musd,
            "rigs": [r.to_dict() for r in self.rigs],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Company:
        return cls(
            name=d["name"],
            cash_musd=d["cash_musd"],
            reputation=d["reputation"],
            debt_musd=d["debt_musd"],
            rigs=[Rig.from_dict(r) for r in d["rigs"]],
        )