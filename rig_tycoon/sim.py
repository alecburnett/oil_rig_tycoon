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
from .rig_market import RigMarketGenerator


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
        self.rig_id_seq = 1000
        self.contract_gen = ContractGenerator(self.rng)
        self.rig_market_gen = RigMarketGenerator(cfg.seed)

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
        self.company_history: list[dict] = []
        self.current_tenders: list[Tender] = []
        self.current_rigs_for_sale: list[RigForSale] = []
        
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
            "rigs": [r.to_dict() for c in self.all_companies for r in c.rigs],
            "companies": [c.to_dict() for c in self.all_companies],
            "contract_id_seq": self.contract_id_seq,
            "rig_id_seq": self.rig_id_seq,
            "current_rigs_for_sale": [r.to_dict() for r in self.current_rigs_for_sale],
            "contract_gen": self.contract_gen.to_dict(),
            "rig_market_gen": self.rig_market_gen.to_dict(),
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
        sim.rig_id_seq = d.get("rig_id_seq", 1000)
        
        sim.oil_market = OilMarket.from_dict(d["markets"]["oil"], sim.rng)
        sim.steel_market = SteelMarket.from_dict(d["markets"]["steel"], sim.rng)
        sim.contract_gen = ContractGenerator.from_dict(d["contract_gen"], sim.rng)
        if "rig_market_gen" in d:
            sim.rig_market_gen = RigMarketGenerator.from_dict(d["rig_market_gen"])
        
        sim.current_rigs_for_sale = []
        if "current_rigs_for_sale" in d:
            from .models import RigForSale
            sim.current_rigs_for_sale = [RigForSale.from_dict(r) for r in d["current_rigs_for_sale"]]
        
        # Reconstruct rigs and link to companies
        all_rigs_list = [Rig.from_dict(r) for r in d.get("rigs", [])]
        rig_map = {r.id: r for r in all_rigs_list}

        sim.all_companies = [Company.from_dict(c, rig_map) for c in d["companies"]]
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
            "demand_factor": round(self.oil_market.demand_factor, 2),
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
                location_id="1",
                model_id="5",
            ),
            Rig(
                id=2,
                rig_type=RigType.JACKUP,
                build_year=self.cfg.start_year - 15,
                condition=62,
                region=Region.GOM,
                state=RigState.COLD,
                location_id="2",
                model_id="3",
            ),
        ]
        return Company(
            id=1,
            name="PlayerCo",
            cash_musd=55.0,
            rigs=rigs,
            reputation=0.55,
        )

    def _make_ai(self) -> list[Company]:
        a = Company(
            id=10,
            name="Stack&Pray Drilling",
            cash_musd=40.0,
            rigs=[
                Rig(
                    id=101,
                    rig_type=RigType.JACKUP,
                    build_year=self.cfg.start_year - 11,
                    condition=74,
                    region=Region.NORTH_SEA,
                    state=RigState.ACTIVE,
                    location_id="3",
                    model_id="12",
                ),
                Rig(
                    id=102,
                    rig_type=RigType.SEMI,
                    build_year=self.cfg.start_year - 9,
                    condition=82,
                    region=Region.NORTH_SEA,
                    state=RigState.ACTIVE,
                    location_id="4",
                    model_id="8",
                ),
            ],
            reputation=0.50,
        )
        b = Company(
            id=20,
            name="Bluewater Titans",
            cash_musd=85.0,
            rigs=[
                Rig(
                    id=201,
                    rig_type=RigType.SEMI,
                    build_year=self.cfg.start_year - 6,
                    condition=90,
                    region=Region.GOM,
                    state=RigState.ACTIVE,
                    location_id="5",
                    model_id="2",
                ),
                Rig(
                    id=202,
                    rig_type=RigType.JACKUP,
                    build_year=self.cfg.start_year - 18,
                    condition=58,
                    region=Region.GOM,
                    state=RigState.COLD,
                    location_id="6",
                    model_id="10",
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
                        r.state = RigState.ACTIVE
                        r.contract_id = None
                else:
                    cost_musd += r.stacking_cost_per_month_k() / 1000.0

            if c.debt_musd > 0:
                cost_musd += c.debt_musd * 0.01

            c.cash_musd += (rev_musd - cost_musd)

    # ======================
    # Auction
    # ======================

    def _award_contracts(self, tenders: list[Tender], player_bids: list[tuple[int, int, int]]) -> list[dict]:
        # Create a map for quick lookup
        p_bid_map: dict[int, tuple[int, int]] = {t_id: (r_id, rate) for t_id, r_id, rate in player_bids}
        awards = []

        for t in tenders:
            bids: list[tuple[str, int, int]] = []

            if t.id in p_bid_map:
                bids.append((self.player.name, *p_bid_map[t.id]))

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
            rig.contract_id = t.id

            awards.append({
                "tender_id": t.id,
                "region": t.spec.region.value,
                "winner": winner,
                "rig_id": rig_id,
                "dayrate_k": dayrate,
                "months": t.spec.months
            })
        
        return awards

    # ======================
    # Views / UI accessors
    # ======================

    def _current_year(self) -> int:
        return self.cfg.start_year + self.oil_market.month // 12

    def _get_company(self, name: str) -> Company:
        try:
            return next(c for c in self.all_companies if c.name == name)
        except StopIteration:
            raise ValueError(f"Company '{name}' not found. Known: {[c.name for c in self.all_companies]}")

    def _forecast_monthly_financials(self, company: Company) -> tuple[float, float]:
        """
        Compute monthly revenue and opex (MUSD) without mutating state.
        """
        year = self._current_year()
        revenue_musd = 0.0
        opex_musd = 0.0
        for r in company.rigs:
            if r.state == RigState.SCRAP:
                continue
            if r.on_contract_months_left > 0:
                revenue_musd += (r.contract_dayrate * 30) / 1000.0
                opex_musd += (r.opex_per_day_k(year) * 30) / 1000.0
            else:
                opex_musd += r.stacking_cost_per_month_k() / 1000.0
        if company.debt_musd > 0:
            opex_musd += company.debt_musd * 0.008
        return revenue_musd, opex_musd

    def get_open_tenders(self) -> list[dict]:
        """
        Return the most recently generated tenders (pre-award) in dict form.
        """
        return [t.to_dict() for t in self.current_tenders]

    def get_company_fleet(self, company_name: str = "PlayerCo") -> list[dict]:
        """
        Snapshot of a company's rigs: specs, location, and live contract info.
        """
        company = self._get_company(company_name)
        year = self._current_year()
        out = []
        for r in company.rigs:
            if r.on_contract_months_left > 0:
                m_opex = r.opex_per_day_k(year) * 30
            else:
                m_opex = r.stacking_cost_per_month_k()

            out.append({
                "id": r.id,
                "type": r.rig_type.value,
                "build_year": r.build_year,
                "condition": r.condition,
                "region": r.region.value,
                "state": r.state.value,
                "location_id": r.location_id,
                "model_id": r.model_id,
                "on_contract_months_left": r.on_contract_months_left,
                "contract_dayrate_k": r.contract_dayrate,
                "contract_id": r.contract_id,
                "transit_months_left": r.transit_months_left,
                "target_region": r.target_region.value if r.target_region else None,
                "monthly_opex_k": m_opex,
            })
        return out

    def get_company_schedule(self, company_name: str = "PlayerCo") -> list[dict]:
        """
        Compact view of per-rig schedules and availability.
        """
        company = self._get_company(company_name)
        items = []
        for r in company.rigs:
            items.append({
                "rig_id": r.id,
                "state": r.state.value,
                "months_left": r.on_contract_months_left,
                "contract_id": r.contract_id,
                "transit_months_left": r.transit_months_left,
                "target_region": r.target_region.value if r.target_region else None,
                "region": r.region.value,
                "available": r.is_available,
            })
        return items

    def get_company_backlog(self, company_name: str = "PlayerCo") -> list[dict]:
        """
        Active contracts with remaining duration and revenue potential.
        """
        company = self._get_company(company_name)
        backlog = []
        for r in company.rigs:
            if r.on_contract_months_left <= 0:
                continue
            backlog.append({
                "rig_id": r.id,
                "contract_id": r.contract_id,
                "months_left": r.on_contract_months_left,
                "dayrate_k": r.contract_dayrate,
                "region": r.region.value,
                "est_monthly_revenue_musd": (r.contract_dayrate * 30) / 1000.0,
            })
        return backlog

    def get_company_finances(self, company_name: str = "PlayerCo") -> dict:
        """
        Returns cash, debt, and simple monthly P&L forecast.
        """
        company = self._get_company(company_name)
        revenue_musd, opex_musd = self._forecast_monthly_financials(company)
        return {
            "cash_musd": company.cash_musd,
            "debt_musd": company.debt_musd,
            "reputation": company.reputation,
            "revenue_musd_month": revenue_musd,
            "opex_musd_month": opex_musd,
            "net_musd_month": revenue_musd - opex_musd,
        }

    # ======================
    # Player bidding (auto)
    # ======================

    def _player_auto_bid(self, tender: Contract) -> tuple[int, int] | None:
        candidates = []
        for r in self.player.rigs:
            if not r.is_available:
                continue
            from .contracts import rig_matches_class
            if not rig_matches_class(r.rig_type, tender.spec.rig_type):
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

        softness = 1.0 - min(1.0, self.oil_market.demand_factor / 1.5)
        discount = int((0.08 + 0.22 * softness) * tender.spec.max_dayrate)
        dayrate = tender.spec.max_dayrate - discount

        breakeven = rig.opex_per_day_k(current_year) + 12
        if dayrate < breakeven - 8:
            return None

        return (rig.id, max(1, dayrate))

    def validate_bid(self, tender: Tender, rig: Rig) -> tuple[bool, str]:
        """
        Returns (is_valid, reason)
        """
        if not rig.is_available:
            return False, f"Rig {rig.id} is not available (state={rig.state.value}, months_left={rig.on_contract_months_left})"
        
        from .contracts import rig_matches_class
        if not rig_matches_class(rig.rig_type, tender.spec.rig_type):
            return False, f"Rig type {rig.rig_type.value} does not match required class {tender.spec.rig_type.name}"
        
        if rig.region != tender.spec.region:
            return False, f"Rig region {rig.region.value} does not match tender region {tender.spec.region.value}"
            
        if rig.condition < tender.spec.min_condition:
            return False, f"Rig condition {rig.condition} is below minimum {tender.spec.min_condition}"
            
        return True, ""

    def buy_rig(self, rig_id: int) -> tuple[bool, str]:
        """
        Attempts to buy a rig from the market.
        Returns (success, message).
        """
        match = next((fs for fs in self.current_rigs_for_sale if fs.rig.id == rig_id), None)
        if not match:
            return False, f"Rig {rig_id} not found in market."
            
        if self.player.cash_musd < match.price_musd:
            return False, f"Insufficient cash. Need ${match.price_musd:0.1f}m, have ${self.player.cash_musd:0.1f}m."
            
        # Purchase
        self.player.cash_musd -= match.price_musd
        new_rig = match.rig
        new_rig.company_id = self.player.id
        self.player.rigs.append(new_rig)
        
        # Remove from market
        self.current_rigs_for_sale = [fs for fs in self.current_rigs_for_sale if fs.rig.id != rig_id]
        
        return True, f"Successfully purchased Rig {rig_id} for ${match.price_musd:0.1f}m."

    def update_rig_state(self, rig_id: int, new_state: RigState) -> tuple[bool, str]:
        """
        Moves rig between ACTIVE, WARM, and COLD.
        """
        rig = next((r for r in self.player.rigs if r.id == rig_id), None)
        if not rig:
            return False, f"Rig {rig_id} not found in your fleet."
        
        if rig.on_contract_months_left > 0:
            return False, f"Rig {rig_id} is on contract and cannot be stacked/reactivated."
            
        if rig.state == new_state:
            return False, f"Rig {rig_id} is already in state {new_state.value}."
            
        cost_musd = 0.0
        msg = ""

        # Transitions
        if rig.state == RigState.COLD and new_state == RigState.WARM:
            cost_musd = 1.2 if rig.rig_type == RigType.JACKUP else 3.5
            msg = f"reactivated to WARM stack. Cost: ${cost_musd:0.1f}m."
        elif rig.state == RigState.WARM and new_state == RigState.ACTIVE:
            cost_musd = 0.3 if rig.rig_type == RigType.JACKUP else 0.8
            msg = f"activated for service. Cost: ${cost_musd:0.1f}m."
        elif rig.state == RigState.ACTIVE and new_state == RigState.WARM:
            cost_musd = 0.05
            msg = f"moved to WARM stack (skeleton crew). Cost: ${cost_musd:0.1f}m."
        elif rig.state == RigState.WARM and new_state == RigState.COLD:
            cost_musd = 0.2
            msg = f"moved to COLD stack. Cost: ${cost_musd:0.1f}m."
        elif rig.state == RigState.COLD and new_state == RigState.ACTIVE:
            # Combined
            cost_musd = (1.2 + 0.3) if rig.rig_type == RigType.JACKUP else (3.5 + 0.8)
            msg = f"fully reactivated from COLD to ACTIVE. Cost: ${cost_musd:0.1f}m."
        elif rig.state == RigState.ACTIVE and new_state == RigState.COLD:
            cost_musd = 0.05 + 0.2
            msg = f"stacked from ACTIVE to COLD. Cost: ${cost_musd:0.1f}m."
        else:
            return False, f"Unsupported transition from {rig.state.value} to {new_state.value}."

        if self.player.cash_musd < cost_musd:
            return False, f"Insufficient cash. Need ${cost_musd:0.2f}m."

        self.player.cash_musd -= cost_musd
        rig.state = new_state
        return True, f"Rig {rig_id} {msg}"

    def scrap_rig(self, rig_id: int) -> tuple[bool, str]:
        """
        Sells rig for scrap value.
        """
        rig = next((r for r in self.player.rigs if r.id == rig_id), None)
        if not rig:
            return False, f"Rig {rig_id} not found in your fleet."
            
        if rig.on_contract_months_left > 0:
            return False, f"Rig {rig_id} is on contract and cannot be scrapped."
            
        # Payout based on type + condition
        base = 8.0 if rig.rig_type == RigType.DRILLSHIP else (5.0 if rig.rig_type == RigType.SEMI else 2.5)
        condition_mult = 0.4 + (rig.condition / 100.0) * 0.6
        payout = round(base * condition_mult, 1)
        
        self.player.cash_musd += payout
        rig.state = RigState.SCRAP
        # Remove from active rigs
        self.player.rigs = [r for r in self.player.rigs if r.id != rig_id]
        
        return True, f"Rig {rig_id} scrapped for ${payout:0.1f}m."

    def mobilize_rig(self, rig_id: int, target_region: Region) -> tuple[bool, str]:
        """
        Starts mobilization to another region.
        """
        rig = next((r for r in self.player.rigs if r.id == rig_id), None)
        if not rig:
            return False, f"Rig {rig_id} not found in your fleet."
            
        if rig.on_contract_months_left > 0:
            return False, f"Rig {rig_id} is on contract and cannot mobilize."
            
        if rig.region == target_region and rig.transit_months_left == 0:
            return False, f"Rig {rig_id} is already in {target_region.value}."
            
        # Cost and Time
        # Very simple: $2.5m and 1 month for any move for now.
        cost_musd = 2.5
        duration_months = 1
        
        if self.player.cash_musd < cost_musd:
            return False, f"Insufficient cash for mobilization. Need ${cost_musd:0.1f}m."
            
        self.player.cash_musd -= cost_musd
        rig.transit_months_left = duration_months
        rig.target_region = target_region
        
        return True, f"Rig {rig_id} started mobilization to {target_region.value}. Cost: ${cost_musd:0.1f}m, Time: {duration_months}m."

    def get_loan_info(self) -> dict:
        """
        Returns (current_debt, max_debt, avail_to_borrow).
        """
        # Max debt = 60% of total scrap value
        total_scrap = 0.0
        for r in self.player.rigs:
            base = 8.0 if r.rig_type == RigType.DRILLSHIP else (5.0 if r.rig_type == RigType.SEMI else 2.5)
            condition_mult = 0.4 + (r.condition / 100.0) * 0.6
            payout = round(base * condition_mult, 1)
            total_scrap += payout
        
        max_debt = round(total_scrap * 0.6, 1)
        return {
            "current_debt": self.player.debt_musd,
            "max_debt": max_debt,
            "available": max(0.0, round(max_debt - self.player.debt_musd, 1))
        }

    def take_loan(self, amount_musd: float) -> tuple[bool, str]:
        info = self.get_loan_info()
        if amount_musd <= 0:
            return False, "Amount must be positive."
        if amount_musd > info["available"]:
            return False, f"Borrowing limit exceeded. Max available: ${info['available']:0.1f}m"
        
        self.player.debt_musd += amount_musd
        self.player.cash_musd += amount_musd
        return True, f"Borrowed ${amount_musd:0.1f}m. Current debt: ${self.player.debt_musd:0.1f}m."

    def repay_loan(self, amount_musd: float) -> tuple[bool, str]:
        if amount_musd <= 0:
            return False, "Amount must be positive."
        if amount_musd > self.player.cash_musd:
            return False, f"Insufficient cash to repay ${amount_musd:0.1f}m."
        
        payment = min(amount_musd, self.player.debt_musd)
        if payment <= 0:
            return False, "No debt to repay."
            
        self.player.cash_musd -= payment
        self.player.debt_musd -= payment
        return True, f"Repaid ${payment:0.1f}m. Remaining debt: ${self.player.debt_musd:0.1f}m."

    # ======================
    # Run loop
    # ======================

    def prepare_turn(self) -> list[Tender]:
        """
        Advance market and generate new tenders.
        Returns newly generated tenders.
        """
        self.oil_market.step_month()
        self.steel_market.step_month()
        
        year = self.cfg.start_year + (self.oil_market.month // 12)
        month = (self.oil_market.month % 12) + 1
        as_of_date = date(year, month, 1)

        tenders, self.contract_id_seq = self.contract_gen.generate_tick(
            regions=[Region.NORTH_SEA, Region.GOM],
            next_contract_id=self.contract_id_seq,
            as_of_date=as_of_date,
            oil_factor=self.oil_market.oil_factor,
            demand_factor=self.oil_market.demand_factor,
        )
        self.current_tenders = tenders

        # Generate new rigs for sale at the start of the turn
        year = self.cfg.start_year + (self.oil_market.month // 12)
        self.current_rigs_for_sale, self.rig_id_seq = self.rig_market_gen.generate_tick(
            current_year=year,
            steel_price=self.steel_market.steel_price,
            next_rig_id=self.rig_id_seq
        )

        return tenders

    def resolve_turn(self, player_bids: list[tuple[int, int, int]]) -> list[dict]:
        """
        Award contracts, settle cashflows, and save state.
        """
        m = self.oil_market.month
        
        awards = self._award_contracts(self.current_tenders, player_bids)
        self._settle_month_cashflows()
        self._record_month()
        
        # Transit progress
        for c in self.all_companies:
            for r in c.rigs:
                if r.transit_months_left > 0:
                    r.transit_months_left -= 1
                    if r.transit_months_left == 0:
                        r.region = r.target_region
                        r.target_region = None
        
        # Save states
        self._save_turn_files(m, self.current_tenders, self.current_rigs_for_sale)

        return awards

    def _save_turn_files(self, m: int, tenders: list[Tender], rigs_for_sale: list) -> None:
        import json
        turn_save = self.output_dir / f"turn_{m:02d}_state.json"
        self.save(turn_save)

        with open(self.output_dir / f"turn_{m:02d}_tenders.json", "w") as f:
            json.dump([t.to_dict() for t in tenders], f, indent=2)

        with open(self.output_dir / f"turn_{m:02d}_rigs_for_sale.json", "w") as f:
            json.dump([r.to_dict() for r in rigs_for_sale], f, indent=2)

        market_state = {
            "oil": self.oil_market.to_dict(),
            "steel": self.steel_market.to_dict(),
        }
        with open(self.output_dir / f"turn_{m:02d}_market.json", "w") as f:
            json.dump(market_state, f, indent=2)

        companies_state = [c.to_dict() for c in self.all_companies]
        with open(self.output_dir / f"turn_{m:02d}_companies.json", "w") as f:
            json.dump(companies_state, f, indent=2)

    def run(self) -> None:
        """Original run loop for automation/testing"""
        for _ in range(self.cfg.months):
            tenders = self.prepare_turn()
            # In auto-run, player still auto-bids
            player_bids = []
            for t in tenders:
                bid = self._player_auto_bid(t)
                if bid:
                    player_bids.append((t.id, *bid))
            
            self.resolve_turn(player_bids)
            self._print_month_summary(tenders)

            if self.player.cash_musd <= 0:
                print("\n💥 BANKRUPT. Game over.\n")
                break

        self.finalize()

    def finalize(self) -> None:
        df_market = pd.DataFrame(self.market_history)
        df_market.to_csv(self.output_dir / "simulation_output_market.csv", index=False)

        df_company = pd.DataFrame(self.company_history)
        df_company.to_csv(self.output_dir / "simulation_output_company.csv", index=False)

        self.save(self.output_dir / "final_state.json")

    # ======================
    # Output
    # ======================

    def _print_month_summary(self, tenders: list[Contract]) -> None:
        m = self.oil_market.month
        print(f"\n=== Month {m:02d} | Oil ${self.oil_market.oil_price:0.1f} | Steel ${self.steel_market.steel_price:0.0f} ===")
        print(f"Tenders: {len(tenders)} | Demand Factor: {self.oil_market.demand_factor:0.2f}")

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
        self._print_player_fleet()

    def _print_player_fleet(self) -> None:
        print("\n🚢 Player Fleet Status:")
        print(f"{'ID':<4} {'Type':<8} {'Location':<18} {'Status':<8} {'Opex':<10} {'Dayrate':<10} {'Schedule'}")
        print("-" * 80)
        
        current_year = self.cfg.start_year + (self.oil_market.month // 12)
        for r in self.player.rigs:
            loc = f"{r.region.value[:10]} ({r.location_id})"
            status = r.state.value.upper()
            
            if r.state == RigState.ACTIVE:
                opex = f"${r.opex_per_day_k(current_year)}k/d"
                dayrate = f"${r.contract_dayrate}k/d"
                schedule = f"{r.on_contract_months_left}m left"
            else:
                opex = f"${r.stacking_cost_per_month_k()}k/m"
                dayrate = "-"
                schedule = "-"
            
            print(f"{r.id:<4} {r.rig_type.value[:8]:<8} {loc:<18} {status:<8} {opex:<10} {dayrate:<10} {schedule}")
