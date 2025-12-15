# Oil Rig Tycoon

A tycoon simulation where you run an offshore drilling contractor. You must manage your rig fleet, bid on contracts, and survive market cycles.

## Setup

1.  **Create a virtual environment**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Running the Simulation

Run the simulation from the project root:

```bash
python3 -m rig_tycoon.cli --months 36 --seed 7
```

**Options:**
- `--months`: Duration of the simulation in months (default: 36)
- `--seed`: Random seed for reproducibility (default: 7)

## Output

Results are saved to `output/<timestamp>/`:
- `sim_history_market.csv`: Market data (oil price, demand).
- `sim_history_company.csv`: Company data (cash, fleet status).

## Visualization

Open `workings/sim_visualisations.ipynb` in Jupyter/VS Code to view charts of the latest simulation run.