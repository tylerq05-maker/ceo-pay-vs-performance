"""Central configuration for the CEO pay vs. performance pipeline.

Every tunable knob lives here so the whole project can be re-scoped
(e.g. sample -> full S&P 500) by changing one value or one env var.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------
# FULL_UNIVERSE=1 runs all ~500 constituents. Default is a 100-company
# sector-stratified sample so the pipeline finishes quickly.
FULL_UNIVERSE: bool = os.getenv("FULL_UNIVERSE", "0") == "1"
SAMPLE_SIZE: int = int(os.getenv("SAMPLE_SIZE", "100"))
RANDOM_SEED: int = 42

# ---------------------------------------------------------------------------
# SEC EDGAR
# ---------------------------------------------------------------------------
# SEC fair-access policy requires a descriptive User-Agent with contact info.
# The e-mail is a placeholder: set SEC_CONTACT_EMAIL before a real run.
SEC_CONTACT_EMAIL: str = os.getenv("SEC_CONTACT_EMAIL", "your.email@example.com")
SEC_USER_AGENT: str = f"Tyler Quezada research {SEC_CONTACT_EMAIL}"
# SEC limit is 10 req/s; stay comfortably below it.
SEC_MAX_REQUESTS_PER_SEC: float = 8.0

# ---------------------------------------------------------------------------
# Analysis settings
# ---------------------------------------------------------------------------
# Primary window (fiscal years) used to pair pay with TSR. 3 years matches the
# standard long-term-incentive performance period. 1y and 5y are robustness.
PRIMARY_WINDOW_YEARS: int = 3
WINDOWS: tuple[int, ...] = (1, 3, 5)
# Flag a company when |proxy TSR - independently computed TSR| exceeds this
# many percentage points of cumulative return.
TSR_DISCREPANCY_PP: float = 10.0
N_OUTLIERS_EACH_SIDE: int = 5
# As-of date for trailing (calendar) TSR used as market context.
AS_OF_DATE: str = os.getenv("AS_OF_DATE", "2026-10-30")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
CHARTS = ROOT / "output" / "charts"
REPORT = ROOT / "output" / "report"

RAW_EDGAR = DATA_RAW / "edgar"
RAW_MARKET = DATA_RAW / "market"
RAW_UNIVERSE = DATA_RAW / "universe"

for _p in (DATA_RAW, DATA_PROCESSED, CHARTS, REPORT, RAW_EDGAR, RAW_MARKET, RAW_UNIVERSE):
    _p.mkdir(parents=True, exist_ok=True)


def scope_label() -> str:
    return "full" if FULL_UNIVERSE else f"sample{SAMPLE_SIZE}"
