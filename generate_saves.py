import sys
from pathlib import Path
from datetime import date

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent))

from rig_tycoon.sim import Sim, SimConfig

def generate_saves():
    print("🔋 Generating sample save files...")
    
    cfg = SimConfig(seed=123, months=24)
    sim = Sim(cfg)
    
    test_date = date(2025, 1, 1)
    
    for month in range(1, 25):
        sim.oil_market.step_month()
        sim.steel_market.step_month()
        tenders, sim.contract_id_seq = sim.contract_gen.generate_tick(
            regions=["NORTH_SEA", "GOM"],
            next_contract_id=sim.contract_id_seq,
            as_of_date=test_date,
            oil_factor=sim.oil_market.oil_factor,
            demand_factor=sim.oil_market.demand_factor,
        )
        sim._award_contracts(tenders)
        sim._settle_month_cashflows()
        sim._record_month()
        
        # Save at specific intervals
        if month == 6:
            sim.save("save_early_game_month_6.json")
        elif month == 12:
            sim.save("save_mid_game_month_12.json")
        elif month == 18:
            sim.save("save_late_game_month_18.json")

    print("\n✨ Done! Generated:")
    print(" - save_early_game_month_6.json")
    print(" - save_mid_game_month_12.json")
    print(" - save_late_game_month_18.json")

if __name__ == "__main__":
    generate_saves()
