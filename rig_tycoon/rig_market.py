from __future__ import annotations
import random
from typing import Optional
from .models import Rig, RigType, Region, RigState, RigForSale

class RigMarketGenerator:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    def generate_tick(self, current_year: int, steel_price: float, next_rig_id: int) -> tuple[list[RigForSale], int]:
        """
        Generates 0-3 second-hand rigs for sale.
        """
        out = []
        rid = next_rig_id

        # Same 0-3 logic as tenders but perhaps lower average?
        # User said "rarely", so let's adjust weights.
        val = 0.8 + self.rng.uniform(-1.0, 1.0) # Lower center than tenders
        n = int(round(val))
        n = max(0, min(3, n))

        for _ in range(n):
            rig_for_sale = self._generate_one(rid, current_year, steel_price)
            out.append(rig_for_sale)
            rid += 1

        return out, rid

    def _generate_one(self, rig_id: int, current_year: int, steel_price: float) -> RigForSale:
        rtype = self.rng.choice(list(RigType))
        
        # Build year: 5 to 35 years old
        age = self.rng.randint(5, 35)
        build_year = current_year - age
        
        # Condition: 30 to 90
        condition = self.rng.randint(30, 90)
        
        # Region: random
        region = self.rng.choice(list(Region))

        rig = Rig(
            id=rig_id,
            rig_type=rtype,
            build_year=build_year,
            condition=condition,
            region=region,
            state=RigState.COLD, # Second hand rigs usually cold stacked
            location_id=str(self.rng.randint(1, 20)),
            model_id=str(self.rng.randint(1, 15)),
        )

        # Price logic: base + condition bonus - age penalty, scaled by steel
        if rtype == RigType.DRILLSHIP:
            base_price = 220.0
        elif rtype == RigType.SEMI:
            base_price = 150.0
        else: # JACKUP
            base_price = 60.0
        
        # Age penalty: -2% per year
        age_factor = 1.0 - (age * 0.02)
        # Condition factor: 0.5 to 1.2
        condition_factor = 0.5 + (condition / 100.0) * 0.7
        
        # Market factor: steel price relative to ~800 baseline
        market_factor = steel_price / 800.0
        
        price = base_price * age_factor * condition_factor * market_factor
        price = max(5.0, round(price, 1)) # Minimum scrap valueish

        return RigForSale(rig=rig, price_musd=price)

    def to_dict(self) -> dict:
        return {
            "rng_state": list(self.rng.getstate()),
        }

    @classmethod
    def from_dict(cls, d: dict) -> RigMarketGenerator:
        gen = cls()
        if "rng_state" in d:
            state = d["rng_state"]
            state_tuple = (state[0], tuple(state[1]), state[2])
            gen.rng.setstate(state_tuple)
        return gen
