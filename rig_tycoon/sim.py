from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random
import pandas as pd

from .models import (
    Company, Rig, RigType, RigState, Region,
    Contract, ContractSpec
)
from .market import OilMarket, SteelMarket
from .ai import AIPersonality, choose_bid
from .contracts import ContractGenerator, Tender


from datetime import datetime, date

# ======================
# Config
# ======================

@dataclass
class SimConfig:
    seed: int = 7
    months: int = 36
    start_year: int = 2025


# ======================
# Simulation
# ======================

class Sim:
    def __init__(self, cfg: SimConfig):
        self.rng = random.Random(cfg.seed)
        self.cfg = cfg
        self.oil_market = OilMarket(rng=self.rng)
        self.steel_market = SteelMarket(rng=self.rng)
        self.contract_id_seq = 1
        self.contract_gen = ContractGenerator(self.rng)

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
        self.market_history: list[dict] = []
        self.demand_history: list[dict] = []
        self.company_history: list[dict] = []
        
        timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
        self.output_dir = Path("output") / timestamp
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ======================
    # Save / Load
    # ======================

    def to_dict(self) -> dict:
        return {
            "save_version": 1,
            "meta": {
                "created_at": datetime.now().isoformat(),
                "game_version": "0.1.0",
            },
            "rng_state": list(self.rng.getstate()),
            "time": {
                "month": self.oil_market.month,
            },
            "markets": {
                "oil": self.oil_market.to_dict(),
                "steel": self.steel_market.to_dict(),
            },
            "companies": [c.to_dict() for c in self.all_companies],
            "contract_id_seq": self.contract_id_seq,
            "contract_gen": self.contract_gen.to_dict(),
        }

    @classmethod
    def load(cls, path: str | Path) -> Sim:
        import json
        with open(path, "r") as f:
            d = json.load(f)

        # Create sim with dummy config, then overwrite
        cfg = SimConfig(seed=0) # Seed will be overwritten by rng_state
        sim = cls(cfg)
        
        state = d["rng_state"]
        # random.setstate expects a 3-tuple, where the second element is a tuple of 624 ints
        # JSON gives us lists, so we must convert them back.
        state_tuple = (
            state[0],
            tuple(state[1]),
            state[2]
        )
        sim.rng.setstate(state_tuple)
        sim.contract_id_seq = d["contract_id_seq"]
        
        sim.oil_market = OilMarket.from_dict(d["markets"]["oil"], sim.rng)
        sim.steel_market = SteelMarket.from_dict(d["markets"]["steel"], sim.rng)
        sim.contract_gen = ContractGenerator.from_dict(d["contract_gen"], sim.rng)
        
        sim.all_companies = [Company.from_dict(c) for c in d["companies"]]
        sim.player = next(c for c in sim.all_companies if c.name == "PlayerCo")
        sim.ai_companies = [c for c in sim.all_companies if c.name != "PlayerCo"]

        return sim

    def save(self, path: str | Path) -> None:
        import json
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        print(f"💾 Game saved to {path}")

    # ======================
    # Logging
    # ======================

    def _record_month(self) -> None:
        # Market grain
        self.market_history.append({
            "month": self.oil_market.month,
            "oil_price": round(self.oil_market.oil_price, 2),
            "steel_price": round(self.steel_market.steel_price, 2),
        })

        # Demand grain
        self.demand_history.append({
            "month": self.oil_market.month,
            "demand_north_sea": round(self.oil_market.demand_north_sea, 2),
            "demand_gom": round(self.oil_market.demand_gom, 2),
            "demand_sea": round(self.oil_market.demand_sea, 2),
            "demand_india": round(self.oil_market.demand_india, 2),
            "demand_middle_east": round(self.oil_market.demand_middle_east, 2),
            "demand_west_africa": round(self.oil_market.demand_west_africa, 2),
            "demand_east_africa": round(self.oil_market.demand_east_africa, 2),
            "demand_brazil": round(self.oil_market.demand_brazil, 2),
            "demand_arctic": round(self.oil_market.demand_arctic, 2),
            "demand_barents": round(self.oil_market.demand_barents, 2),
        })

        # Company grain
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

            self.company_history.append({
                "month": self.oil_market.month,
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
                build_year=self.cfg.start_year - 8,
                condition=78,
                region=Region.NORTH_SEA,
                state=RigState.WARM,
            ),
            Rig(
                id=2,
                rig_type=RigType.JACKUP,
                build_year=self.cfg.start_year - 15,
                condition=62,
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
                    build_year=self.cfg.start_year - 11,
                    condition=74,
                    region=Region.NORTH_SEA,
                    state=RigState.WARM,
                ),
                Rig(
                    id=102,
                    rig_type=RigType.SEMI,
                    build_year=self.cfg.start_year - 9,
                    condition=82,
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
                    build_year=self.cfg.start_year - 6,
                    condition=90,
                    region=Region.GOM,
                    state=RigState.WARM,
                ),
                Rig(
                    id=202,
                    rig_type=RigType.JACKUP,
                    build_year=self.cfg.start_year - 18,
                    condition=58,
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


    # ======================
    # Cashflows
    # ======================

    def _settle_month_cashflows(self) -> None:
        current_year = self.cfg.start_year + self.oil_market.month // 12
        for c in self.all_companies:
            rev_musd = 0.0
            cost_musd = 0.0

            for r in c.rigs:
                if r.state == RigState.SCRAP:
                    continue

                if r.on_contract_months_left > 0:
                    rev_musd += (r.contract_dayrate * 30) / 1000.0
                    cost_musd += (r.opex_per_day_k(current_year) * 30) / 1000.0

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

    def _award_contracts(self, tenders: list[Tender]) -> None:
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
            if r.condition < tender.spec.min_condition:
                continue
            candidates.append(r)

        if not candidates:
            return None

        current_year = tender.spec.start_date.year
        candidates.sort(key=lambda r: (r.opex_per_day_k(current_year), -r.condition))
        rig = candidates[0]

        softness = 1.0 - min(
            1.0,
            self.oil_market.regional_demand(tender.spec.region) / 3.0
        )
        discount = int((0.08 + 0.22 * softness) * tender.spec.max_dayrate)
        dayrate = tender.spec.max_dayrate - discount

        breakeven = rig.opex_per_day_k(current_year) + 12
        if dayrate < breakeven - 8:
            return None

        return (rig.id, max(1, dayrate))

    # ======================
    # Run loop
    # ======================

    def run(self) -> None:
        for _ in range(self.cfg.months):
            self.oil_market.step_month()
            self.steel_market.step_month()
            # Calculate approximate date for contracts
            year = self.cfg.start_year + (self.oil_market.month // 12)
            month = (self.oil_market.month % 12) + 1
            as_of_date = date(year, month, 1)

            tenders, self.contract_id_seq = self.contract_gen.generate_tick(
                regions=["NORTH_SEA", "GOM"],
                next_contract_id=self.contract_id_seq,
                as_of_date=as_of_date,
            )
            self._award_contracts(tenders)
            self._settle_month_cashflows()
            self._record_month()
            self._print_month_summary(tenders)

            if self.player.cash_musd <= 0:
                print("\n💥 BANKRUPT. Game over.\n")
                break

        df_market = pd.DataFrame(self.market_history)
        out_market = self.output_dir / "simulation_output_market.csv"
        df_market.to_csv(out_market, index=False)

        df_demand = pd.DataFrame(self.demand_history)
        out_demand = self.output_dir / "simulation_output_regional_demand.csv"
        df_demand.to_csv(out_demand, index=False)

        df_company = pd.DataFrame(self.company_history)
        out_company = self.output_dir / "simulation_output_company.csv"
        df_company.to_csv(out_company, index=False)

        # Save final state JSON
        out_save = self.output_dir / "final_state.json"
        self.save(out_save)

        print(f"\n📊 Simulation history written to:")
        print(f"  - {out_market.resolve()}")
        print(f"  - {out_demand.resolve()}")
        print(f"  - {out_company.resolve()}")
        print(f"  - {out_save.resolve()}")

    # ======================
    # Output
    # ======================

    def _print_month_summary(self, tenders: list[Contract]) -> None:
        m = self.oil_market.month
        print(f"\n=== Month {m:02d} | Oil ${self.oil_market.oil_price:0.1f} | Steel ${self.steel_market.steel_price:0.0f} ===")
        print(
            f"Tenders: {len(tenders)} | "
            f"Demand NS={self.oil_market.demand_north_sea:0.2f} "
            f"GOM={self.oil_market.demand_gom:0.2f}"
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