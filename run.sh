#!/bin/bash
# Ensure we run from the project root
cd "$(dirname "$0")"

# Run the simulation module
python3 -m rig_tycoon.cli "$@"
