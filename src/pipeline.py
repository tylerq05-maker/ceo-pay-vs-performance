"""Run the whole project end to end.

    python -m src.pipeline                 # 100-company sample (default)
    FULL_UNIVERSE=1 python -m src.pipeline # all ~500 S&P 500 companies
    python -m src.pipeline --notebook      # also execute notebooks/analysis.ipynb

Every step reads/writes files under data/ and output/, and all downloads are
cached in data/raw, so re-runs make no network requests.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

from . import (analysis, backtest, build_dataset, charts, compensation, config, market_data, outlier_evidence,
               replication, report, screener, strategy, universe, validate)

STEPS = [
    ("Phase 1  universe + stratified sample", lambda: universe.build()),
    ("Phase 2  SEC EDGAR pay-versus-performance + SCT", lambda: compensation.run()),
    ("Phase 3  market data, TSR, fundamentals", lambda: market_data.run()),
    ("Phase 4a master dataset", lambda: build_dataset.build()),
    ("Phase 5a say-on-pay votes (8-K Item 5.07)", lambda: outlier_evidence.run_say_on_pay()),
    ("Phase 4b statistical analysis", lambda: analysis.run()),
    ("Phase 5b outlier proxy evidence", lambda: outlier_evidence.run()),
    ("Phase 4c strategy test: does excess pay predict returns?", lambda: strategy.run()),
    ("Phase 4d portfolio backtest", lambda: backtest.run()),
    ("Validation suite", lambda: validate.run()),
    ("Replication vs. full S&P 500 (needs a FULL_UNIVERSE=1 run first)", lambda: replication.run()),
    ("Phase 6a charts", lambda: charts.run()),
    ("Phase 6b report", lambda: report.build()),
    ("Phase 6c interactive screener", lambda: screener.build()),
]
# The report, screener and notebook narrate the 100-company study (its case
# studies, outlier ranks and screenshots); the full universe is a replication.
SAMPLE_ONLY = {"Phase 5b outlier proxy evidence", "Phase 6b report", "Phase 6c interactive screener",
               "Replication vs. full S&P 500 (needs a FULL_UNIVERSE=1 run first)"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--notebook", action="store_true", help="execute notebooks/analysis.ipynb at the end")
    args = ap.parse_args()
    print(f"Scope: {config.scope_label()} | SEC User-Agent: {config.SEC_USER_AGENT}")
    t0 = time.time()
    for name, fn in STEPS:
        if config.FULL_UNIVERSE and name in SAMPLE_ONLY:
            print(f"\n=== {name}: skipped for the full universe ===")
            continue
        t = time.time()
        print(f"\n=== {name} ===")
        fn()
        print(f"--- done in {time.time() - t:.1f}s")
    if args.notebook and not config.FULL_UNIVERSE:
        print("\n=== Executing notebooks/analysis.ipynb ===")
        subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
                        "--ExecutePreprocessor.timeout=600", str(config.ROOT / "notebooks" / "analysis.ipynb")],
                       check=True)
    print(f"\nPipeline finished in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
