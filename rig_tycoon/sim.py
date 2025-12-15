from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random
import pandas as pd

from .models import (
    Company, Rig, RigType, RigState, Region,
    Contract, ContractSpec
)
from .market import Market
from .ai import AIPersonality, choose_bid


# ======================
# Config
# ======================

@dataclass
class SimConfig:
    seed: int = 7
    months: int = 36


# ======================
# Simulation
# ======================

class Sim:
    def __init__(self, cfg: SimConfig):
        self.rng = random.Random(cfg.seed)
        self.cfg = cfg
        self.market = Market(rng=self.rng)
        self.contract_id_seq = 1

        self.player = self._make_player()
        self.ai_companies = self._make_ai()
        self.all_companies = [self.player] + self.ai_companies

        # AI personalities
        self.ai_personalities = {
            self.ai_companies[0].name: AIPersonality(
                aggressiveness=0.75,
                desperation=0.55,
                quality_bias=0.2,
            ),
            self.ai_companies[1].name: AIPersonality(
                aggressiveness=0.35,
                desperation=0.25,
                quality_bias=0.6,
            ),
        }

        # logging
        self.history: list[dict] = []
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)

    # ======================
    # Logging
    # ======================

    def _record_month(self) -> None:
        for c in self.all_companies:
            active = sum(1 for r in c.rigs if r.on_contract_months_left > 0)
            warm = sum(
                1 for r in c.rigs
                if r.on_contract_months_left == 0 and r.state == RigState.WARM
            )
            cold = sum(
                1 for r in c.rigs
                if r.on_contract_months_left == 0 and r.state == RigState.COLD
            )

            self.history.append({
                "month": self.market.month,
                "oil_price": round(self.market.oil_price, 2),
                "demand_ns": round(self.market.demand_north_sea, 2),
                "demand_gom": round(self.market.demand_gom, 2),
                "company": c.name,
                "cash_musd": round(c.cash_musd, 2),
                "rigs_active": active,
                "rigs_warm": warm,
                "rigs_cold": cold,
            })

    # ======================
    # Setup
    # ======================

    def _make_player(self) -> Company:
        rigs = [
            Rig(
                id=1,
                rig_type=RigType.JACKUP,
                age_years=8,
                spec=78,
                region=Region.NORTH_SEA,
                state=RigState.WARM,
            ),
            Rig(
                id=2,
                rig_type=RigType.JACKUP,
                age_years=15,
                spec=62,
                region=Region.GOM,
                state=RigState.COLD,
            ),
        ]
        return Company(
            name="PlayerCo",
            cash_musd=55.0,
            rigs=rigs,
            reputation=0.55,
        )

    def _make_ai(self) -> list[Company]:
        a = Company(
            name="Stack&Pray Drilling",
            cash_musd=40.0,
            rigs=[
                Rig(
                    id=101,
                    rig_type=RigType.JACKUP,
                    age_years=11,
                    spec=74,
                    region=Region.NORTH_SEA,
                    state=RigState.WARM,
                ),
                Rig(
                    id=102,
                    rig_type=RigType.SEMI,
                    age_years=9,
                    spec=82,
                    region=Region.NORTH_SEA,
                    state=RigState.WARM,
                ),
            ],
            reputation=0.50,
        )
        b = Company(
            name="Bluewater Titans",
            cash_musd=85.0,
            rigs=[
                Rig(
                    id=201,
                    rig_type=RigType.SEMI,
                    age_years=6,
                    spec=90,
                    region=Region.GOM,
                    state=RigState.WARM,
                ),
                Rig(
                    id=202,
                    rig_type=RigType.JACKUP,
                    age_years=18,
                    spec=58,
                    region=Region.GOM,
                    state=RigState.COLD,
                ),
            ],
            reputation=0.65,
        )
        return [a, b]

    # ======================
    # Contracts
    # ======================

    def _generate_contracts(self) -> list[Contract]:
        tenders: list[Contract] = []

        for region in (Region.NORTH_SEA, Region.GOM):
            demand = self.market.regional_demand(region)

            n = max(0, int(round(demand + self.rng.random() * 1.5)))

            for _ in range(n):
                harsh = region == Region.NORTH_SEA and self.rng.random() < 0.45

                rig_type = (
                    RigType.SEMI if harsh and self.rng.random() < 0.6
                    else RigType.JACKUP
                )
                months = self.rng.choice([6, 9, 12, 18, 24])
                min_spec = 70 if harsh else self.rng.choice([55, 60, 65, 70])

                base = 140 if rig_type == RigType.JACKUP else 260
                oil_factor = (self.market.oil_price - 40) / 50
                max_dayrate = int(
                    base * (0.65 + 0.65 * max(0.0, min(1.4, oil_factor)))
                )
                if harsh:
                    max_dayrate = int(max_dayrate * 1.15)

                spec = ContractSpec(
                    region=region,
                    months=months,
                    rig_type=rig_type,
                    min_spec=min_spec,
                    harsh=harsh,
                    max_dayrate=max_dayrate,
                )

                tenders.append(
                    Contract(id=self.contract_id_seq, spec=spec)
                )
                self.contract_id_seq += 1

        return tenders

    # ======================
    # Cashflows
    # ======================

    def _settle_month_cashflows(self) -> None:
        for c in self.all_companies:
            rev_musd = 0.0
            cost_musd = 0.0

            for r in c.rigs:
                if r.state == RigState.SCRAP:
                    continue

                if r.on_contract_months_left > 0:
                    rev_musd += (r.contract_dayrate * 30) / 1000.0
                    cost_musd += (r.opex_per_day_k() * 30) / 1000.0

                    r.on_contract_months_left -= 1
                    if r.on_contract_months_left == 0:
                        r.contract_dayrate = 0
                        r.state = RigState.WARM
                else:
                    cost_musd += r.stacking_cost_per_month_k() / 1000.0

            if c.debt_musd > 0:
                cost_musd += c.debt_musd * 0.008

            c.cash_musd += (rev_musd - cost_musd)

    # ======================
    # Auction
    # ======================

    def _award_contracts(self, tenders: list[Contract]) -> None:
        for t in tenders:
            bids: list[tuple[str, int, int]] = []

            player_bid = self._player_auto_bid(t)
            if player_bid:
                bids.append((self.player.name, *player_bid))

            for ai in self.ai_companies:
                p = self.ai_personalities[ai.name]
                ai_bid = choose_bid(ai, p, t)
                if ai_bid:
                    bids.append((ai.name, *ai_bid))

            if not bids:
                continue

            scored = []
            for company_name, rig_id, dayrate in bids:
                comp = next(x for x in self.all_companies if x.name == company_name)
                rep_penalty = (1.0 - comp.reputation) * 4.0
                scored.append((dayrate + rep_penalty, company_name, rig_id, dayrate))

            scored.sort(key=lambda x: x[0])
            _, winner, rig_id, dayrate = scored[0]

            comp = next(x for x in self.all_companies if x.name == winner)
            rig = next(r for r in comp.rigs if r.id == rig_id)

            rig.on_contract_months_left = t.spec.months
            rig.contract_dayrate = dayrate
            rig.state = RigState.ACTIVE

    # ======================
    # Player bidding (auto)
    # ======================

    def _player_auto_bid(self, tender: Contract) -> tuple[int, int] | None:
        candidates = []
        for r in self.player.rigs:
            if not r.is_available:
                continue
            if r.rig_type != tender.spec.rig_type:
                continue
            if r.region != tender.spec.region:
                continue
            if r.spec < tender.spec.min_spec:
                continue
            candidates.append(r)

        if not candidates:
            return None

        candidates.sort(key=lambda r: (r.opex_per_day_k(), -r.spec))
        rig = candidates[0]

        softness = 1.0 - min(
            1.0,
            self.market.regional_demand(tender.spec.region) / 3.0
        )
        discount = int((0.08 + 0.22 * softness) * tender.spec.max_dayrate)
        dayrate = tender.spec.max_dayrate - discount

        breakeven = rig.opex_per_day_k() + 12
        if dayrate < breakeven - 8:
            return None

        return (rig.id, max(1, dayrate))

    # ======================
    # Run loop
    # ======================

    def run(self) -> None:
        for _ in range(self.cfg.months):
            self.market.step_month()
            tenders = self._generate_contracts()
            self._award_contracts(tenders)
            self._settle_month_cashflows()
            self._record_month()
            self._print_month_summary(tenders)

            if self.player.cash_musd <= 0:
                print("\n💥 BANKRUPT. Game over.\n")
                break

        df = pd.DataFrame(self.history)
        out = self.output_dir / "sim_history.csv"
        df.to_csv(out, index=False)
        print(f"\n📊 Simulation history written to {out.resolve()}")

    # ======================
    # Output
    # ======================

    def _print_month_summary(self, tenders: list[Contract]) -> None:
        m = self.market.month
        print(f"\n=== Month {m:02d} | Oil ${self.market.oil_price:0.1f} ===")
        print(
            f"Tenders: {len(tenders)} | "
            f"Demand NS={self.market.demand_north_sea:0.2f} "
            f"GOM={self.market.demand_gom:0.2f}"
        )

        for c in self.all_companies:
            active = sum(1 for r in c.rigs if r.on_contract_months_left > 0)
            warm = sum(
                1 for r in c.rigs
                if r.on_contract_months_left == 0 and r.state == RigState.WARM
            )
            cold = sum(
                1 for r in c.rigs
                if r.on_contract_months_left == 0 and r.state == RigState.COLD
            )
            print(
                f"- {c.name:18s} "
                f"cash=${c.cash_musd:6.1f}m | "
                f"rigs active={active} warm={warm} cold={cold}"
            )