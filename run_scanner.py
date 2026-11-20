#!/usr/bin/env python3
"""
Entry point for the TESS Continuous Scan Daemon.
"""
import argparse
import sys
from pipeline.continuous_scanner import ContinuousScanner

def main():
    parser = argparse.ArgumentParser(
        description="Astro Sentinel — Continuous Autonomous TESS Scan"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between TESS/MAST queries to avoid rate limits (default: 0.5s)"
    )
    parser.add_argument(
        "--targets-file",
        type=str,
        default=None,
        help="Optional file with TIC IDs to scan, one per line"
    )
    parser.add_argument(
        "--max-targets",
        type=int,
        default=None,
        help="Maximum targets to evaluate (omit for infinite continuous scan)"
    )

    args = parser.parse_args()

    targets = None
    if args.targets_file:
        try:
            with open(args.targets_file, "r", encoding="utf-8") as f:
                targets = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except Exception as e:
            print(f"Error reading {args.targets_file}: {e}")
            sys.exit(1)

    scanner = ContinuousScanner(delay_between_targets=args.delay)
    scanner.run_continuous_scan(custom_targets=targets, max_iterations=args.max_targets)

if __name__ == "__main__":
    main()
