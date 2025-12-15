from __future__ import annotations
from dataclasses import dataclass, field
import random
from collections import deque
from .models import Region


@dataclass
class Market:
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