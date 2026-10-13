#!/usr/bin/env python3
"""Entry: awg-panel-serve."""
from awg_panel.config import load_config
from awg_panel.server import run

if __name__ == "__main__":
    run(load_config())
