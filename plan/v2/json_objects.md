# Oil Rig Tycoon — Save Game JSON Schema

This document defines **what a save file must contain** to fully restore a game of *Oil Rig Tycoon* and continue the simulation deterministically.

> **Design rule**
> If you load the JSON and continue ticking the simulation, the game should behave **exactly as if it had never been closed**.

---

## Top-level structure

```json
{
  "save_version": 1,
  "meta": { ... },
  "rng_state": ...,
  "time": { ... },
  "markets": { ... },
  "companies": [ ... ],
  "contracts": { ... }
}
```

---

## 1. `meta`

Save bookkeeping and human-readable context.

```json
"meta": {
  "created_at": "2025-12-16T14:03:12",
  "game_version": "0.1.0",
  "notes": "Autosave before bankruptcy"
}
```

Used for:

* compatibility checks
* UI labels ("Month 23 autosave")
* debugging old saves

---

## 2. `rng_state` (required)

Stores the Python RNG state to guarantee deterministic continuation.

```json
"rng_state": [
  3,
  [123456789, 987654321, 456789123, 1122334455],
  null
]
```

Source:

```python
rng.getstate()
```

Without this, AI bidding, market evolution, and contract generation will diverge after reload.

---

## 3. `time`

Tracks the current simulation position.

```json
"time": {
  "month": 17,
  "current_date": "2027-05-01"
}
```

This should align with:

* monthly tick counter
* contract start dates
* market lag logic

---

## 4. `markets`

All market state that affects future ticks must be saved **as-is**.

```json
"markets": {
  "oil": {
    "oil_price": 71.3,
    "trend": -0.03
  },
  "steel": {
    "steel_price": 612.0,
    "trend": 0.01
  }
}
```

Rule:

> If a value influences future behaviour, it must be saved — not recomputed.

---

## 5. `companies`

Each company is self-contained and owns its rigs.

```json
"companies": [
  {
    "name": "PlayerCo",
    "cash_musd": 42.7,
    "debt_musd": 15.0,
    "reputation": 0.56,
    "rigs": ['1', '2', '3']
  }
]
```

### Rigs (nested)

```json
"rigs": [
  {
    "rig_id": 1,
    "model_id": 234,
    "rig_type": "JACKUP",
    "built": "2025-01-01",
    "max_water_depth_m": 76,
    "condition_pct": 100,
    "region": "NORTH_SEA",
    "location_id": 1,
    "state": "ACTIVE",
    "contract_id": 5,
    "crew_id": 1
  }
]
```

Do **not** save derived metrics (utilisation, cashflow, etc.).

---

## 6. `contracts`

```json
"contracts": {
  "contract_id": 8373,  
  "tender_id": 143,
  "company_id": 1,
  "rig_id": 201,
  "bid_dayrate_k": 265,
  "start_date": "2027-06-01",
  "end_date": "2028-06-01",
  "status": "ACTIVE",   ["mobilising", "active", "demobilising", "completed", "cancelled", "paused"]
}
```

### Open tenders

```json
"open_tenders": [
  {
    "tender_id": 141,
    "contract_type": "DEVELOPMENT",
    "region": "GOM",
    "start_date": "2027-06-01",
    "duration_months": 12,
    "water_depth_m": 320,
    "harsh_required": false,
    "rig_class_required": "SEMI",
    "positioning_required": "MORED_OK",
    "dayrate_k_min": 180,
    "dayrate_k_max": 240,
    "early_termination_penalty_k": 7200,
    "month_delays_tolerated": 2,
    "mobilisation_included": true,
  }
]
```


This separation cleanly supports:

* auction logic
* delayed starts
* penalties and failures

---

## What NOT to save

Do **not** include:

* CSV / Pandas history tables
* Derived metrics
* Debug output
* Anything recomputable in one tick

Those belong to analytics, not game state.

---

## Versioning note

Always include `save_version`.
Future migrations can be handled with small transformation functions:

```python
if save_version == 1:
    migrate_v1_to_v2(data)
```

---

**This schema is intentionally boring — and that’s a compliment.**
Boring saves mean reliable tycoon drama.
