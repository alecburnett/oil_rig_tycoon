import argparse
import sys
from .sim import Sim, SimConfig


def print_fleet(sim: Sim):
    fleet = sim.get_company_fleet()
    print("\n🚢 YOUR FLEET")
    print(f"{'ID':<5} {'Type':<10} {'Region':<12} {'Status':<12} {'Months':<8} {'Dayrate':<10} {'Opex':<8} {'Cond'}")
    print("-" * 80)
    for r in fleet:
        status = r["state"].upper()
        region_str = r["region"]
        if r["transit_months_left"] > 0:
            status = f"TRANSIT({r['transit_months_left']}m)"
            region_str = f"{r['region']}->{r['target_region']}"
            
        months = r["on_contract_months_left"] if r["on_contract_months_left"] > 0 else "-"
        dayrate = f"${r['contract_dayrate_k']}k" if r["contract_dayrate_k"] > 0 else "-"
        print(f"{r['id']:<5} {r['type']:<10} {region_str:<12} {status:<12} {months:<8} {dayrate:<10} ${r['monthly_opex_k']:<7} {r['condition']}%")


def print_tenders(sim: Sim):
    tenders = sim.get_open_tenders()
    print("\n📝 OPEN TENDERS")
    print(f"{'ID':<5} {'Type':<12} {'Region':<12} {'Rig Class':<18} {'Term':<6} {'Cond':<6} {'Dayrate Range':<15}")
    print("-" * 85)
    from .ai import suggest_bid
    for t in tenders:
        spec = t["spec"]
        dr_range = f"${spec['min_dayrate']}-{spec['max_dayrate']}k"
        print(f"{t['id']:<5} {spec['contract_type']:<12} {spec['region']:<12} {spec['rig_type']:<18} {spec['months']:<6} {spec['min_condition']}% {dr_range:<15}")
        
        # Suggested bid helper
        suggestion = suggest_bid(sim.player, sim.current_tenders[tenders.index(t)])
        if "error" not in suggestion:
            print(f"      💡 Suggestion: Rig {suggestion['best_rig_id']} | Breakeven ${suggestion['breakeven_k']}k | Range ${suggestion['suggested_min_k']}-${suggestion['suggested_max_k']}k")


def print_market(sim: Sim):
    market = sim.current_rigs_for_sale
    print("\n🚢 RIG MARKET (SECOND-HAND)")
    if not market:
        print("No rigs currently for sale.")
        return
    print(f"{'ID':<5} {'Type':<10} {'Region':<12} {'Year':<6} {'Cond':<6} {'Price':<10}")
    print("-" * 55)
    for fs in market:
        r = fs.rig
        print(f"{r.id:<5} {r.rig_type.value:<10} {r.region.value:<12} {r.build_year:<6} {r.condition:<6} ${fs.price_musd:0.1f}m")


def print_awards(awards: list[dict]):
    print("\n🏆 AUCTION RESULTS")
    if not awards:
        print("No contracts were awarded this month.")
        return
    print(f"{'Tender':<8} {'Region':<12} {'Winner':<20} {'Rig':<6} {'Dayrate':<10} {'Term':<6}")
    print("-" * 65)
    for a in awards:
        print(f"{a['tender_id']:<8} {a['region']:<12} {a['winner']:<20} {a['rig_id']:<6} ${a['dayrate_k']:<10} {a['months']}m")


def print_companies(sim: Sim):
    print("\n🏢 COMPANY OVERVIEW")
    print(f"{'Name':<22} {'Cash':<10} {'Rigs':<6} {'Revenue':<12} {'Rep':<6}")
    print("-" * 60)
    for c in sim.all_companies:
        fin = sim.get_company_finances(c.name)
        active_rigs = [r for r in c.rigs if r.on_contract_months_left > 0]
        rig_count_str = f"{len(active_rigs)}/{len(c.rigs)}"
        print(f"{c.name:<22} ${fin['cash_musd']:<9.1f} {rig_count_str:<6} ${fin['revenue_musd_month']:<11.2f} {c.reputation:0.2f}")


def print_regions():
    from .models import Region
    print("\n🌍 GLOBAL DRILLING REGIONS")
    print(f"{'Name':<20} {'ID'}")
    print("-" * 35)
    for reg in Region:
        print(f"{reg.name:<20} {reg.value}")


def print_status(sim: Sim):
    fin = sim.get_company_finances()
    m = sim.oil_market.month
    print(f"\n🌍 MONTH {m:02} | Oil: ${sim.oil_market.oil_price:0.1f} | Steel: ${sim.steel_market.steel_price:0.0f} | Demand: {sim.oil_market.demand_factor:0.2f}")
    
    market_count = len(sim.current_rigs_for_sale)
    market_alert = f" | 🚢 {market_count} rigs for sale!" if market_count > 0 else ""
    
    net_val = fin['net_musd_month']
    net_str = f"{'+' if net_val >=0 else '-'}{abs(net_val):0.2f}m"
    
    cash_line = f"💰 Cash: ${fin['cash_musd']:0.1f}m | Monthly Net: {net_str}{market_alert}"
    if sim.player.debt_musd > 0:
        info = sim.get_loan_info()
        cash_line += f" | 🏦 Debt: ${sim.player.debt_musd:0.1f}m (limit ${info['max_debt']}m)"
    print(cash_line)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--months", type=int, default=36)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--load", type=str, help="Path to save game to load")
    args = p.parse_args()

    if args.load:
        sim = Sim.load(args.load)
        print(f"📂 Loaded game from {args.load}")
    else:
        sim = Sim(SimConfig(seed=args.seed, months=args.months))
        print("🚀 Starting new simulation")

    player_bids = []
    
    # Initial tenders
    sim.prepare_turn()

    while True:
        print_status(sim)
        print("\nVIEWS:   fleet, tenders, market, companies, regions")
        print("ACTIONS: next, bid, stack, reactivate, mobilize, buy, scrap, loan, repay, save, help, quit")
        cmd_raw = input("> ").strip().lower()
        if not cmd_raw:
            continue
            
        parts = cmd_raw.split()
        cmd = parts[0]

        if cmd == "next":
            awards = sim.resolve_turn(player_bids)
            print("\n" + "="*40 + "\nADVANCING TO NEXT MONTH\n" + "="*40)
            print_awards(awards)
            
            player_bids = []
            if sim.player.cash_musd <= 0:
                print("\n💥 BANKRUPT. Game over.\n")
                break
            sim.prepare_turn()
        elif cmd == "fleet":
            print_fleet(sim)
            
        elif cmd == "tenders":
            print_tenders(sim)
            
        elif cmd == "bid":
            if len(parts) < 3:
                print("❌ Usage: bid <tender_id> <rig_id> <rate_k>  (or: bid <tender_id> <rate_k> if you only have one eligible rig)")
                continue
            try:
                # Case: bid <t_id> <rate> (3 parts)
                if len(parts) == 3:
                    t_id = int(parts[1])
                    rate = int(parts[2])
                    
                    tender = next((t for t in sim.current_tenders if t.id == t_id), None)
                    if not tender:
                        print(f"❌ Tender {t_id} not found.")
                        continue
                        
                    # Find eligible rigs
                    eligible = []
                    for r in sim.player.rigs:
                        valid, _ = sim.validate_bid(tender, r)
                        if valid:
                            eligible.append(r)
                            
                    if len(eligible) == 0:
                        print(f"❌ You have no eligible rigs for Tender {t_id}.")
                        # Show why?
                        for r in sim.player.rigs:
                            _, reason = sim.validate_bid(tender, r)
                            print(f"   - Rig {r.id}: {reason}")
                        continue
                    elif len(eligible) > 1:
                        print(f"❌ Multiple rigs are eligible ({[r.id for r in eligible]}). Please specify: bid {t_id} <rig_id> {rate}")
                        continue
                    else:
                        r_id = eligible[0].id
                        rig = eligible[0]
                else:
                    # Case: bid <t_id> <r_id> <rate> (4 parts)
                    t_id = int(parts[1])
                    r_id = int(parts[2])
                    rate = int(parts[3])
                    
                    tender = next((t for t in sim.current_tenders if t.id == t_id), None)
                    rig = next((r for r in sim.player.rigs if r.id == r_id), None)
                    
                    if not tender:
                        print(f"❌ Tender {t_id} not found.")
                        continue
                    if not rig:
                        print(f"❌ Rig {r_id} not found in your fleet.")
                        continue
                        
                    valid, reason = sim.validate_bid(tender, rig)
                    if not valid:
                        print(f"❌ Invalid bid: {reason}")
                        continue
                
                # Check if rate is within reason
                if rate > tender.spec.max_dayrate:
                    print(f"⚠️ Warning: Bid ${rate}k exceeds operator's max willingness of ${tender.spec.max_dayrate}k. You will likely lose.")
                
                # Replace if already bid on this tender
                player_bids = [b for b in player_bids if b[0] != t_id]
                player_bids.append((t_id, r_id, rate))
                print(f"✅ Bid recorded: Rig {r_id} on Tender {t_id} for ${rate}k/day")
                
            except ValueError:
                print("❌ IDs and rate must be integers.")
                
        elif cmd == "market":
            print_market(sim)
            
        elif cmd == "companies":
            print_companies(sim)
            
        elif cmd == "regions":
            print_regions()
            
        elif cmd == "buy":
            if len(parts) < 2:
                print("❌ Usage: buy <rig_id>")
                continue
            try:
                r_id = int(parts[1])
                success, msg = sim.buy_rig(r_id)
                if success:
                    print(f"✅ {msg}")
                else:
                    print(f"❌ {msg}")
            except ValueError:
                print("❌ Rig ID must be an integer.")
                
        elif cmd == "stack":
            if len(parts) < 3:
                print("❌ Usage: stack <rig_id> <warm|cold>")
                continue
            try:
                r_id = int(parts[1])
                from .models import RigState
                state_map = {"active": RigState.ACTIVE, "warm": RigState.WARM, "cold": RigState.COLD}
                if parts[2] not in state_map:
                    print("❌ State must be 'active', 'warm' or 'cold'.")
                    continue
                success, msg = sim.update_rig_state(r_id, state_map[parts[2]])
                if success:
                    print(f"✅ {msg}")
                else:
                    print(f"❌ {msg}")
            except ValueError:
                print("❌ Rig ID must be an integer.")

        elif cmd == "reactivate":
            if len(parts) < 2:
                print("❌ Usage: reactivate <rig_id>")
                continue
            try:
                r_id = int(parts[1])
                from .models import RigState
                # Find current rig to see what we're reactivating FROM
                rig = next((r for r in sim.player.rigs if r.id == r_id), None)
                if not rig:
                    print(f"❌ Rig {r_id} not found.")
                    continue
                
                # If warm, move to active. If cold, move to warm.
                target_state = RigState.ACTIVE if rig.state == RigState.WARM else RigState.WARM
                success, msg = sim.update_rig_state(r_id, target_state)
                if success:
                    print(f"✅ {msg}")
                else:
                    print(f"❌ {msg}")
            except ValueError:
                print("❌ Rig ID must be an integer.")

        elif cmd == "mobilize":
            if len(parts) < 3:
                print("❌ Usage: mobilize <rig_id> <region>")
                print("   Regions: north_sea, gom, brazil, west_africa, southeast_asia, australia")
                continue
            try:
                r_id = int(parts[1])
                from .models import Region
                try:
                    target_reg = Region(parts[2])
                except ValueError:
                    print(f"❌ Invalid region. Choose from: {[reg.value for reg in Region]}")
                    continue
                    
                success, msg = sim.mobilize_rig(r_id, target_reg)
                if success:
                    print(f"✅ {msg}")
                else:
                    print(f"❌ {msg}")
            except ValueError:
                print("❌ Rig ID must be an integer.")

        elif cmd == "scrap":
            if len(parts) < 2:
                print("❌ Usage: scrap <rig_id>")
                continue
            try:
                r_id = int(parts[1])
                # Double confirm?
                confirm = input(f"Are you sure you want to scrap Rig {r_id}? (y/n): ").strip().lower()
                if confirm == 'y':
                    success, msg = sim.scrap_rig(r_id)
                    if success:
                        print(f"✅ {msg}")
                    else:
                        print(f"❌ {msg}")
            except ValueError:
                print("❌ Rig ID must be an integer.")

        elif cmd == "loan":
            if len(parts) < 2:
                info = sim.get_loan_info()
                print(f"🏦 BANK OF OFFSHORE")
                print(f"   Current Debt: ${info['current_debt']:0.1f}m")
                print(f"   Borrow Limit: ${info['max_debt']:0.1f}m")
                print(f"   Available:    ${info['available']:0.1f}m")
                print(f"   Interest:     1.0% monthly")
                print("\n   Usage: loan <amount>")
                continue
            try:
                amt = float(parts[1])
                success, msg = sim.take_loan(amt)
                if success:
                    print(f"✅ {msg}")
                else:
                    print(f"❌ {msg}")
            except ValueError:
                print("❌ Amount must be a number.")

        elif cmd == "repay":
            if len(parts) < 2:
                print("❌ Usage: repay <amount>")
                continue
            try:
                amt = float(parts[1])
                success, msg = sim.repay_loan(amt)
                if success:
                    print(f"✅ {msg}")
                else:
                    print(f"❌ {msg}")
            except ValueError:
                print("❌ Amount must be a number.")

        elif cmd == "save":
            path = parts[1] if len(parts) > 1 else "quicksave.json"
            sim.save(path)
            
        elif cmd == "help":
            print("\n📈 VIEWS")
            print("  fleet            - View your rigs, status, and opex")
            print("  tenders          - View open contracts and suggested bids")
            print("  market           - View second-hand rigs available for sale")
            print("  companies        - Compare cash, rigs, and rep of all firms")
            print("  regions          - List global regions and their IDs")
            
            print("\n🚀 ACTIONS")
            print("  next             - Advance to next month (resolves bids)")
            print("  bid ...          - bid <t_id> <r_id> <rate> or bid <t_id> <rate>")
            print("  stack <id> <st>  - Move rig to 'active', 'warm' or 'cold'")
            print("  reactivate <id>  - Move cold rig to warm, or warm to active")
            print("  mobilize <id> <rg> - Move rig to another region ($2.5m, 1m transit)")
            print("  buy <id>         - Purchase a rig from the market")
            print("  scrap <id>       - Sell a rig for scrap value")
            print("  loan [amt]       - Take out a bank loan (view info or borrow)")
            print("  repay <amt>      - Repay debt to the bank")
            print("  save [path]      - Save current simulation state")
            print("  quit             - Exit game")
            
        elif cmd == "quit":
            break
        else:
            print(f"❓ Unknown command: {cmd}")

    sim.finalize()
    print("\n📊 Simulation finished.")


if __name__ == "__main__":
    main()
