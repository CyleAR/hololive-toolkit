from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from classification import LANGUAGES
from downloader import count_database_jobs, download_database
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
        description="Download, decrypt, and extract Hololive Dreams server assets."
    )
    parser.add_argument(
        "--cache",
        default=str(TOOL_ROOT / "cache" / "octocacheevai"),
        help="Path to octocacheevai",
    )
    parser.add_argument(
        "--inspect", action="store_true", help="Only show database information"
    )
    parser.add_argument(
        "--output", help="Output directory (defaults to cache/extract or cache/download)"
    )
    parser.add_argument(
        "--bundle-cache",
        default=str(TOOL_ROOT / "cache" / "bundles"),
        help="Shared cache for downloaded Unity bundles",
    )
    parser.add_argument(
        "--resource-cache",
        default=str(TOOL_ROOT / "cache" / "resources"),
        help="Shared cache for ACB/AWB and other converted media sources",
    )
    parser.add_argument("--kind", choices=("all", "asset", "resource"), default="all")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--match", help="Case-insensitive regular expression for names")
    parser.add_argument("--limit", type=int, help="Maximum per selected kind")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--language", choices=LANGUAGES, default="jpn")
    parser.add_argument(
        "--categories",
        default="all",
        help="Comma-separated (default: all): img,adv,live2d,model,motion,effect,audio,video,chart,all",
    )
    parser.add_argument(
        "--raw-assets", action="store_true", help="Keep asset bundle headers obfuscated"
    )
    parser.add_argument(
        "--raw-resources", action="store_true", help="Keep the QUAVMAGIC wrapper"
    )
    parser.add_argument(
        "--bundle-key", help="16-byte Unity bundle key (text, hex, or base64)"
    )
    parser.add_argument(
        "--movie-key", help="64-bit CRI Movie key (decimal or 0x-prefixed hex)"
    )
    parser.add_argument(
        "--no-extract",
        action="store_false",
        dest="extract_assets",
        help="Only download and decrypt; do not extract Unity objects or convert media",
    )
    parser.add_argument(
        "--no-convert-videos",
        action="store_false",
        dest="convert_videos",
        help="Extract Unity objects but keep USM videos without creating MP4 files",
    )
    parser.set_defaults(extract_assets=True, convert_videos=True)
    parser.add_argument("--json", dest="json_path", help="Also write full manifest JSON")
    return parser


def _normalize_legacy_command(argv: list[str]) -> list[str]:
    """Keep the former download/inspect command forms working."""
    if not argv:
        return argv
    if argv[0] == "download":
        return argv[1:]
    if argv[0] == "inspect":
        return ["--inspect", *argv[1:]]
    return argv


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(_normalize_legacy_command(raw_argv))
    database = load_database(args.cache)
    summary = database_summary(database)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.json_path:
        write_manifest_json(database, args.json_path)
        print(f"Manifest written: {Path(args.json_path).resolve()}")

    if args.inspect:
        return 0

    counts = {
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "extractedObjects": 0,
        "warnings": 0,
    }
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
    extraction_enabled = args.extract_assets
    convert_videos = extraction_enabled and args.convert_videos
    output_root = args.output or str(
        TOOL_ROOT / "cache" / ("extract" if extraction_enabled else "download")
    )
    results = download_database(
        database,
        output_root,
        bundle_cache_root=args.bundle_cache,
        resource_cache_root=args.resource_cache,
        kind=args.kind,
        workers=args.workers,
        match=args.match,
        limit=args.limit,
        timeout=args.timeout,
        overwrite=args.overwrite,
        deobfuscate=not args.raw_assets,
        decrypt_resources=not args.raw_resources,
        extract_assets=extraction_enabled,
        bundle_key=args.bundle_key,
        language=args.language,
        categories=args.categories,
        convert_videos=convert_videos,
        movie_key=args.movie_key,
        remove_usm=convert_videos,
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
