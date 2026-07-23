from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from downloader import count_database_jobs, download_database
from classification import LANGUAGES
from manifest import database_summary, load_database, write_manifest_json
from rich.console import Console
from rich.text import Text


TOOL_ROOT = Path(__file__).resolve().parent
CONSOLE = Console(highlight=False)


def _print_result(current: int, total: int, result) -> None:
    status_styles = {
        "downloaded": "bold green",
        "skipped": "bold yellow",
        "failed": "bold red",
    }
    line = Text()
    line.append(f"[{current}/{total}] ", style="bold cyan")
    line.append(f"{result.status.upper():10} ", style=status_styles[result.status])
    line.append(f"{result.kind}/{result.category} ", style="bold magenta")
    line.append(result.name)
    if result.status == "failed" and result.error:
        line.append(f"  {result.error}", style="red")
    CONSOLE.print(line)

    if result.warning:
        warning = Text("             WARNING ", style="bold yellow")
        warning.append(f"{result.name}: {result.warning}", style="yellow")
        CONSOLE.print(warning)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decrypt Hololive Dreams' Octo cache and download server assets."
    )
    parser.add_argument(
        "--cache",
        default=str(TOOL_ROOT / "cache" / "octocacheevai"),
        help="Path to octocacheevai",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Show database information")
    inspect_parser.add_argument("--json", dest="json_path", help="Write full manifest JSON")

    def add_transfer_arguments(command_parser, *, extraction_mode: bool) -> None:
        default_dir = "extract" if extraction_mode else "download"
        command_parser.add_argument(
            "--output", default=str(TOOL_ROOT / "cache" / default_dir)
        )
        command_parser.add_argument(
            "--kind", choices=("all", "asset", "resource"), default="all"
        )
        command_parser.add_argument("--workers", type=int, default=12)
        command_parser.add_argument(
            "--match", help="Case-insensitive regular expression for names"
        )
        command_parser.add_argument("--limit", type=int, help="Maximum per selected kind")
        command_parser.add_argument("--timeout", type=float, default=60.0)
        command_parser.add_argument("--overwrite", action="store_true")
        command_parser.add_argument(
            "--language",
            choices=LANGUAGES,
            default="jpn" if extraction_mode else "all",
        )
        command_parser.add_argument(
            "--categories",
            default="img,adv" if extraction_mode else None,
            help="Comma-separated: img,adv,live2d,model,motion,effect,audio,video,chart,all",
        )
        command_parser.add_argument(
            "--raw-assets", action="store_true", help="Keep asset bundle headers obfuscated"
        )
        command_parser.add_argument(
            "--raw-resources", action="store_true", help="Keep the QUAVMAGIC wrapper"
        )
        command_parser.add_argument(
            "--bundle-key", help="16-byte Unity bundle key (text, hex, or base64)"
        )
        if not extraction_mode:
            command_parser.add_argument(
                "--extract-assets",
                action="store_true",
                help="Also export Texture2D, Sprite, TextAsset, and AudioClip",
            )
        else:
            command_parser.set_defaults(extract_assets=True)
        command_parser.add_argument(
            "--json", dest="json_path", help="Also write full manifest JSON"
        )

    download_parser = subparsers.add_parser(
        "download", help="Download, decrypt, and classify server objects"
    )
    add_transfer_arguments(download_parser, extraction_mode=False)

    extract_parser = subparsers.add_parser(
        "extract", help="Download classified objects and export supported Unity payloads"
    )
    add_transfer_arguments(extract_parser, extraction_mode=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    database = load_database(args.cache)
    summary = database_summary(database)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if getattr(args, "json_path", None):
        write_manifest_json(database, args.json_path)
        print(f"Manifest written: {Path(args.json_path).resolve()}")

    if args.command == "inspect":
        return 0

    counts = {"downloaded": 0, "skipped": 0, "failed": 0, "extractedObjects": 0, "warnings": 0}
    total = count_database_jobs(
        database,
        kind=args.kind,
        match=args.match,
        limit=args.limit,
        language=args.language,
        categories=args.categories,
    )
    CONSOLE.print(
        f"[bold blue]>>> [Info][/bold blue] Items to process: [bold cyan]{total}[/bold cyan]"
    )
    results = download_database(
        database,
        args.output,
        kind=args.kind,
        workers=args.workers,
        match=args.match,
        limit=args.limit,
        timeout=args.timeout,
        overwrite=args.overwrite,
        deobfuscate=not args.raw_assets,
        decrypt_resources=not args.raw_resources,
        extract_assets=getattr(args, "extract_assets", False),
        bundle_key=args.bundle_key,
        language=args.language,
        categories=args.categories,
    )
    for current, result in enumerate(results, start=1):
        counts[result.status] += 1
        counts["extractedObjects"] += result.extracted
        if result.warning:
            counts["warnings"] += 1
        _print_result(current, total, result)

    summary_style = "bold red" if counts["failed"] else "bold green"
    CONSOLE.print(
        Text(
            "Completed: " + json.dumps(counts, ensure_ascii=False),
            style=summary_style,
        )
    )
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
