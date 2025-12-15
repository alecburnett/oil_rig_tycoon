from __future__ import annotations
from dataclasses import dataclass, field
import random
from collections import deque
from .models import Region


@dataclass
class OilMarket:
    rng: random.Random
    month: int = 0

    # oil price model
    oil_price: float = 70.0
    mean_price: float = 70.0
    reversion: float = 0.08     # monthly mean reversion
    shock_sd: float = 5.0       # random volatility

    # lagged demand signal (months)
    lag_months: int = 9
    oil_history: deque[float] = field(default_factory=lambda: deque(maxlen=36))

    # demand by region (rig-months per month)
    demand_north_sea: float = 2.0
    demand_gom: float = 2.5
    demand_sea: float = 2.0
    demand_india: float = 2.0
    demand_middle_east: float = 3.0
    demand_west_africa: float = 1.5
    demand_east_africa: float = 0.5
    demand_brazil: float = 2.0
    demand_arctic: float = 0.5
    demand_barents: float = 1

    def step_month(self) -> None:
        self.month += 1

        # mean-reverting random walk
        shock = self.rng.gauss(0, self.shock_sd)
        self.oil_price += self.reversion * (self.mean_price - self.oil_price) + shock
        self.oil_price = max(25.0, min(140.0, self.oil_price))

        self.oil_history.append(self.oil_price)

        # lagged price drives demand (smoothed)
        lag_idx = -self.lag_months
        lag_price = self.oil_history[lag_idx] if len(self.oil_history) >= self.lag_months else self.oil_price

        # map lag_price -> demand multiplier
        # 50 => weak, 80 => strong, 110 => boom
        mult = max(0.4, min(1.8, (lag_price - 30) / 50))

        # region sensitivities
        self.demand_north_sea = 1.5 * mult
        self.demand_gom = 2.2 * mult

    def regional_demand(self, region: Region) -> float:
        return self.demand_north_sea if region == Region.NORTH_SEA else self.demand_gom


@dataclass
class SteelMarket:
    rng: random.Random
    month: int = 0

    # steel price model (e.g. $/tonne or index)
    steel_price: float = 800.0
    mean_price: float = 800.0
    reversion: float = 0.10      # monthly mean reversion
    shock_sd: float = 60.0       # volatility

    # bounds
    floor: float = 350.0
    cap: float = 1800.0

    # lagged demand signal (months)
    lag_months: int = 6
    steel_history: deque[float] = field(default_factory=lambda: deque(maxlen=36))

    # global steel demand (e.g. rig-equivalents / month)
    demand_global: float = 2.0

    def step_month(self) -> None:
        self.month += 1

        # mean-reverting random walk
        shock = self.rng.gauss(0.0, self.shock_sd)
        self.steel_price += self.reversion * (self.mean_price - self.steel_price) + shock
        self.steel_price = max(self.floor, min(self.cap, self.steel_price))

        self.steel_history.append(self.steel_price)

        # lagged price drives demand
        if len(self.steel_history) >= self.lag_months:
            lag_price = self.steel_history[-self.lag_months]
        else:
            lag_price = self.steel_price

        # map lag_price -> demand multiplier
        # 550 => weak, 850 => normal, 1200 => boom
        mult = (lag_price - 450.0) / 500.0
        mult = max(0.5, min(1.8, mult))

        # base global demand tuned for steel-intensive construction cycles
        self.demand_global = 2.0 * mult