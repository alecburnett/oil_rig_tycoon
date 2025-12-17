import sys
import os
from pathlib import Path
import json
from datetime import date

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from rig_tycoon.sim import Sim, SimConfig

def test_save_load():
    print("🚀 Starting Save/Load Determinism Test...")
    
    # 1. Initialize Sim with fixed seed
    cfg = SimConfig(seed=42, months=10)
    sim1 = Sim(cfg)
    
    test_date = date(2025, 1, 1)
    
    # 2. Run for 5 months
    print("\n--- Running Sim 1 for 5 months ---")
    for _ in range(5):
        sim1.oil_market.step_month()
        sim1.steel_market.step_month()
        # Use regions that the generator expects
        tenders, sim1.contract_id_seq = sim1.contract_gen.generate_tick(
            regions=["NORTH_SEA", "GOM"],
            next_contract_id=sim1.contract_id_seq,
            as_of_date=test_date,
            oil_factor=sim1.oil_market.oil_factor,
            demand_factor=sim1.oil_market.demand_factor,
        )
        sim1._award_contracts(tenders)
        sim1._settle_month_cashflows()
        sim1._record_month()
    
    # 3. Save state
    save_path = "test_save.json"
    sim1.save(save_path)
    
    # 4. Load state into Sim 2
    print("\n--- Loading Sim 2 from save ---")
    sim2 = Sim.load(save_path)
    
    # 5. Run both for another 5 months
    print("\n--- Continuing both simulations for 5 more months ---")
    for i in range(5):
        # Sim 1 step
        sim1.oil_market.step_month()
        sim1.steel_market.step_month()
        tenders1, sim1.contract_id_seq = sim1.contract_gen.generate_tick(
            regions=["NORTH_SEA", "GOM"],
            next_contract_id=sim1.contract_id_seq,
            as_of_date=test_date,
            oil_factor=sim1.oil_market.oil_factor,
            demand_factor=sim1.oil_market.demand_factor,
        )
        sim1._award_contracts(tenders1)
        sim1._settle_month_cashflows()
        sim1._record_month()
        
        # Sim 2 step
        sim2.oil_market.step_month()
        sim2.steel_market.step_month()
        tenders2, sim2.contract_id_seq = sim2.contract_gen.generate_tick(
            regions=["NORTH_SEA", "GOM"],
            next_contract_id=sim2.contract_id_seq,
            as_of_date=test_date,
            oil_factor=sim2.oil_market.oil_factor,
            demand_factor=sim2.oil_market.demand_factor,
        )
        sim2._award_contracts(tenders2)
        sim2._settle_month_cashflows()
        sim2._record_month()
        
        # Compare key metrics
        import math
        assert math.isclose(sim1.oil_market.oil_price, sim2.oil_market.oil_price, rel_tol=1e-8), f"Month {i+6} Oil Price mismatch: {sim1.oil_market.oil_price} != {sim2.oil_market.oil_price}"
        assert math.isclose(sim1.player.cash_musd, sim2.player.cash_musd, rel_tol=1e-8), f"Month {i+6} Player Cash mismatch: {sim1.player.cash_musd} != {sim2.player.cash_musd}"
        assert sim1.contract_id_seq == sim2.contract_id_seq, f"Month {i+6} Contract ID mismatch!"
        
        print(f"✅ Month {i+6} identical: Oil=${sim1.oil_market.oil_price:.2f}, Cash=${sim1.player.cash_musd:.2f}m")

    print("\n✨ ALL TESTS PASSED! Save/Load is perfectly deterministic.")
    
    # Cleanup
    if os.path.exists(save_path):
        os.remove(save_path)

if __name__ == "__main__":
    try:
        test_save_load()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
