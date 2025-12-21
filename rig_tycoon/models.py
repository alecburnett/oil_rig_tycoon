from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RigType(str, Enum):
    JACKUP = "jackup"
    SEMI = "semisub"
    DRILLSHIP = "drillship"


class RigState(str, Enum):
    ACTIVE = "active"
    WARM = "warm"
    COLD = "cold"
    SCRAP = "scrap"


class Region(str, Enum):
    NORTH_SEA = "north_sea"
    GOM = "gom"
    BRAZIL = "brazil"
    WEST_AFRICA = "west_africa"
    SE_ASIA = "se_asia"
    AUSTRALIA = "australia"

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
    location_id: Optional[str] = None
    model_id: Optional[str] = None
    company_id: Optional[int] = None
    transit_months_left: int = 0
    target_region: Optional[Region] = None

    def to_dict(self) -> dict:
        out = {
            "id": self.id,
        }
        if self.model_id is not None:
            out["model_id"] = self.model_id
            
        out.update({
            "rig_type": self.rig_type.value,
            "build_year": self.build_year,
            "condition": self.condition,
            "region": self.region.value,
            "state": self.state.value,
        })
        if self.transit_months_left > 0:
            out["transit_months_left"] = self.transit_months_left
        if self.target_region is not None:
            out["target_region"] = self.target_region.value
        if self.on_contract_months_left > 0:
            out["on_contract_months_left"] = self.on_contract_months_left
        if self.contract_dayrate > 0:
            out["contract_dayrate"] = self.contract_dayrate
        if self.contract_id is not None:
            out["contract_id"] = self.contract_id
        if self.location_id is not None:
            out["location_id"] = self.location_id
        if self.company_id is not None:
            out["company_id"] = self.company_id
        return out

    @classmethod
    def from_dict(cls, d: dict) -> Rig:
        return cls(
            id=d["id"],
            rig_type=RigType(d["rig_type"]),
            build_year=d["build_year"],
            condition=d["condition"],
            region=Region(d["region"]),
            state=RigState(d["state"]),
            on_contract_months_left=d.get("on_contract_months_left", 0),
            contract_dayrate=d.get("contract_dayrate", 0),
            contract_id=d.get("contract_id"),
            location_id=d.get("location_id"),
            model_id=d.get("model_id"),
            company_id=d.get("company_id"),
            transit_months_left=d.get("transit_months_left", 0),
            target_region=Region(d["target_region"]) if d.get("target_region") else None,
        )

    @property
    def is_available(self) -> bool:
        return self.state == RigState.ACTIVE and self.on_contract_months_left == 0 and self.transit_months_left == 0

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
        if self.state == RigState.ACTIVE:
            return 850 if self.rig_type == RigType.JACKUP else 1400
        if self.state == RigState.WARM:
            return 450 if self.rig_type == RigType.JACKUP else 750
        if self.state == RigState.COLD:
            return 180
        return 0


@dataclass
class Company:
    id: int
    name: str
    cash_musd: float
    rigs: list[Rig] = field(default_factory=list)
    debt_musd: float = 0.0
    reputation: float = 0.5

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "cash_musd": self.cash_musd,
            "reputation": self.reputation,
            "debt_musd": self.debt_musd,
            "rigs": [{"id": r.id, "location_id": r.location_id} for r in self.rigs],
        }

    @classmethod
    def from_dict(cls, d: dict, rig_map: dict[int, Rig] | None = None) -> Company:
        rigs = []
        if rig_map:
            for r_data in d["rigs"]:
                rid = r_data["id"]
                if rid in rig_map:
                    rigs.append(rig_map[rid])
        
        return cls(
            id=d["id"],
            name=d["name"],
            cash_musd=d["cash_musd"],
            reputation=d["reputation"],
            debt_musd=d["debt_musd"],
            rigs=rigs,
        )


@dataclass
class RigForSale:
    rig: Rig
    price_musd: float

    def to_dict(self) -> dict:
        return {
            "rig": self.rig.to_dict(),
            "price_musd": self.price_musd,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RigForSale:
        return cls(
            rig=Rig.from_dict(d["rig"]),
            price_musd=d["price_musd"],
        )