from __future__ import annotations
import argparse
from .sim import Sim, SimConfig


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--months", type=int, default=36)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()

    sim = Sim(SimConfig(seed=args.seed, months=args.months))
    sim.run()


if __name__ == "__main__":
    main()
