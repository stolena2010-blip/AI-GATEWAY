#!/usr/bin/env python3
"""
DrawingAI Pro — Generic Pipeline Runner
=========================================

Entry point for running any document processing profile.

Usage:
    python run_pipeline.py --profile quotes
    python run_pipeline.py --profile invoices
    python run_pipeline.py --profile quotes --once
    python run_pipeline.py --list
"""

import argparse
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from src.utils.logger import setup_logging, get_logger

setup_logging(log_level="INFO", log_dir=Path("logs"))
logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="DrawingAI Pro — Generic Document Pipeline Runner"
    )
    parser.add_argument(
        "--profile", "-p",
        type=str,
        help="Profile name to run (e.g., quotes, orders, invoices, delivery, complaints)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single processing cycle and exit",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available profiles and exit",
    )
    parser.add_argument(
        "--configs-dir",
        type=str,
        default=None,
        help="Path to configs directory (default: ./configs/)",
    )

    args = parser.parse_args()

    configs_dir = Path(args.configs_dir) if args.configs_dir else None

    # List mode
    if args.list:
        from engine.document_pipeline import load_all_profiles
        profiles = load_all_profiles(configs_dir)
        if not profiles:
            print("No profiles found in configs/")
            return
        print(f"\nAvailable profiles ({len(profiles)}):")
        print("-" * 50)
        for p in profiles:
            engine_type = p.get("ai_engine", {}).get("type", "?")
            print(f"  {p['profile_name']:<15} {p.get('display_name', ''):<20} [{engine_type}]")
        print()
        return

    # Profile required for run
    if not args.profile:
        parser.error("--profile is required (or use --list)")

    from engine.document_pipeline import load_profile, DocumentPipeline

    try:
        profile = load_profile(args.profile, configs_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    def status_cb(msg):
        print(msg)

    pipeline = DocumentPipeline(profile, status_callback=status_cb)

    if args.once:
        # Single cycle
        logger.info(f"Running single cycle for profile: {args.profile}")
        result = pipeline.run_once()
        logger.info(f"Cycle complete: {result}")
    else:
        # Continuous mode with graceful shutdown
        logger.info(f"Starting continuous pipeline for profile: {args.profile}")

        def _signal_handler(sig, frame):
            logger.info(f"Signal {sig} received — stopping pipeline...")
            pipeline.stop()

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        pipeline.start()

        # Block main thread until pipeline stops
        try:
            while pipeline.is_alive:
                pipeline._thread.join(timeout=1)
        except KeyboardInterrupt:
            pipeline.stop()

    logger.info(f"Pipeline '{args.profile}' finished.")


if __name__ == "__main__":
    main()
