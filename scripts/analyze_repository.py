"""Run the canonical analysis workflow from the command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.analysis_service import analysis_service


def main() -> None:
    """Parse CLI arguments and print one JSON report."""
    parser = argparse.ArgumentParser(
        description="Analyze a public GitHub repository."
    )

    parser.add_argument(
        "repository_url",
        help="Public GitHub repository URL.",
    )

    parser.add_argument(
        "--profile",
        default="standard",
        help="Analysis profile. Default: standard.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output file.",
    )

    arguments = parser.parse_args()

    report = analysis_service.analyze_repository_sync(
        repository_url=arguments.repository_url,
        analysis_profile=arguments.profile,
    )

    report_json = report.model_dump_json(indent=2)

    if arguments.output:
        arguments.output.write_text(
            report_json,
            encoding="utf-8",
        )
        print(f"Report written to {arguments.output}")
    else:
        print(report_json)


if __name__ == "__main__":
    main()