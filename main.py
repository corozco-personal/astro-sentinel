#!/usr/bin/env python3
"""
Astro Sentinel CLI for single-target analysis.
"""
import argparse
import sys
from pipeline.pipeline import BlackHolePipeline

def main():
    parser = argparse.ArgumentParser(
        description="Astro Sentinel — Undocumented Black Hole Candidate Search in TESS"
    )
    parser.add_argument(
        "--target",
        type=str,
        default="TIC 261136679",
        help="TESS target identifier (e.g. 'TIC 261136679')"
    )
    parser.add_argument(
        "--sector",
        type=int,
        default=None,
        help="Specific TESS observation sector (optional)"
    )

    args = parser.parse_args()

    pipeline = BlackHolePipeline()
    result = pipeline.analyze_target(args.target, sector=args.sector)

    if result.get("status") == "SUCCESS":
        print("\n[Results]")
        print(f"Target: {result['target_id']}")
        print(f"Verdict: {result['assessment']['verdict']}")
        print(f"Report saved to: {result['report_path']}")
    else:
        print(f"\n[Error] {result.get('reason')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
