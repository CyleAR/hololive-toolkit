from __future__ import annotations

import hashlib
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests

import octodb_pb2
from audio_converter import extract_cri_audio
from classification import classify_name, language_matches, parse_categories
from crypto_utils import RESOURCE_MAGIC, deobfuscate_asset, deobfuscate_resource
from extractor import extract_asset_bundle, parse_bundle_key
from media_converter import convert_usm_to_mp4, parse_movie_key, validate_mp4


_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_thread_local = threading.local()


@dataclass(frozen=True)
class DownloadResult:
    kind: str
    name: str
    category: str
    status: str
    path: Path | None = None
    error: str | None = None
    extracted: int = 0
    warning: str | None = None


def _session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers["User-Agent"] = "hololive-toolkit/1.0"
        _thread_local.session = session
    return session


def _safe_name(name: str, fallback: str) -> str:
    cleaned = _INVALID_FILENAME.sub("_", name).strip(" .")
    return cleaned or fallback


def _object_url(url_format: str, item: octodb_pb2.Data) -> str:
    # Hololive Dreams currently uses https://asset.game-hololive-dreams.com/{o}.
    return url_format.replace("{o}", quote(item.objectName, safe=""))


def _adopt_legacy_bundle(
    destination: Path,
    output_root: Path,
    bundle_cache_root: Path,
    category: str,
    filename: str,
) -> None:
    """Move an older bundle layout into the shared cache when encountered."""
    cache_root = bundle_cache_root.parent
    candidates = (
        output_root / "bundles" / category / filename,
        output_root / "asset" / filename,
        cache_root / "extract" / "bundles" / category / filename,
        cache_root / "download" / "bundles" / category / filename,
        cache_root / "download" / "asset" / filename,
    )
    destination_path = os.path.normcase(os.path.abspath(destination))
    for candidate in candidates:
        if os.path.normcase(os.path.abspath(candidate)) == destination_path:
            continue
        if not candidate.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(candidate, destination)
        except FileExistsError:
            pass
        return


def _adopt_legacy_resource(
    destination: Path,
    output_root: Path,
    category: str,
    filename: str,
) -> None:
    candidate = output_root / category / filename
    if not candidate.exists():
        return
    if os.path.normcase(os.path.abspath(candidate)) == os.path.normcase(
        os.path.abspath(destination)
    ):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(candidate, destination)
    except FileExistsError:
        pass


def _download_one(
    item: octodb_pb2.Data,
    kind: str,
    url_format: str,
    output_root: Path,
    bundle_cache_root: Path,
    resource_cache_root: Path,
    timeout: float,
    overwrite: bool,
    deobfuscate: bool,
    decrypt_resources: bool,
    extract_assets: bool,
    bundle_key: bytes | None,
    convert_videos: bool,
    movie_key: int | None,
    remove_usm: bool,
) -> DownloadResult:
    category = classify_name(item.name, kind)
    suffix = ".unity3d" if kind == "asset" else ""
    filename = _safe_name(item.name, f"object_{item.id}") + suffix
    resource_suffix = Path(filename).suffix.lower()
    cached_media = kind == "resource" and extract_assets and decrypt_resources and (
        (
            category in {"voice", "bgm", "se", "audio"}
            and resource_suffix in {".acb", ".awb"}
        )
        or (category == "video" and resource_suffix == ".usm")
    )
    if kind == "asset":
        destination = bundle_cache_root / category / filename
        if not destination.exists() and not overwrite:
            _adopt_legacy_bundle(
                destination, output_root, bundle_cache_root, category, filename
            )
    elif cached_media:
        destination = resource_cache_root / category / filename
        if not destination.exists() and not overwrite:
            _adopt_legacy_resource(destination, output_root, category, filename)
    elif decrypt_resources:
        destination = output_root / category / filename
    else:
        destination = output_root / "resources-raw" / category / filename

    if (
        kind == "resource"
        and category == "video"
        and convert_videos
        and decrypt_resources
        and destination.suffix.lower() == ".usm"
        and not overwrite
    ):
        mp4 = output_root / category / destination.with_suffix(".mp4").name
        if mp4.exists() and validate_mp4(mp4) is None:
            warning = None
            if remove_usm and destination.exists():
                try:
                    destination.unlink()
                except OSError as exc:
                    warning = f"MP4 is valid, but the USM could not be removed: {exc}"
            return DownloadResult(
                kind, item.name, category, "skipped", mp4, warning=warning
            )

    if destination.exists() and not overwrite:
        extracted = 0
        warning = None
        if kind == "asset" and extract_assets:
            target = output_root / category
            result = extract_asset_bundle(
                destination,
                target,
                bundle_key,
                texture_subdirectory="textures" if category == "model" else None,
                textures_only=category == "model",
            )
            extracted = len(result.outputs)
            warning = result.warning
        elif (
            kind == "resource"
            and category == "video"
            and convert_videos
            and decrypt_resources
            and destination.suffix.lower() == ".usm"
        ):
            result = convert_usm_to_mp4(
                destination,
                output=output_root / category / destination.with_suffix(".mp4").name,
                movie_key=movie_key,
                overwrite=overwrite,
                delete_source=remove_usm,
            )
            extracted = 1 if result.output else 0
            warning = result.warning
        elif (
            kind == "resource"
            and category in {"voice", "bgm", "se", "audio"}
            and extract_assets
            and decrypt_resources
            and destination.suffix.lower() in {".acb", ".awb"}
        ):
            result = extract_cri_audio(
                destination,
                output_root=output_root / category,
                overwrite=overwrite,
            )
            extracted = len(result.outputs)
            warning = result.warning
        return DownloadResult(
            kind, item.name, category, "skipped", destination, extracted=extracted, warning=warning
        )

    try:
        url = _object_url(url_format, item)
        response = _session().get(url, timeout=timeout)
        response.raise_for_status()
        raw = response.content
        if item.size and len(raw) != item.size:
            raise ValueError(f"size mismatch: server={len(raw)} manifest={item.size}")

        if item.md5:
            digest = hashlib.md5(raw).hexdigest()
            if digest.lower() != item.md5.lower():
                raise ValueError(f"MD5 mismatch: server={digest} manifest={item.md5}")

        was_encrypted_resource = raw.startswith(RESOURCE_MAGIC)
        if kind == "asset" and deobfuscate:
            output = deobfuscate_asset(raw, item.name)
        elif kind == "resource" and decrypt_resources:
            output = deobfuscate_resource(raw, item.name)
        else:
            output = raw
        if kind == "asset" and deobfuscate and not output.startswith(b"Unity"):
            raise ValueError("asset header is not Unity after Octo deobfuscation")
        if kind == "resource" and decrypt_resources and was_encrypted_resource:
            expected = {
                ".acb": b"@UTF",
                ".acf": b"@UTF",
                ".awb": b"AFS2",
                ".usm": b"CRID",
                ".sus": b"#",
            }.get(Path(item.name).suffix.lower())
            if expected and not output.startswith(expected):
                raise ValueError(
                    f"resource header is not {expected!r} after QUAVMAGIC deobfuscation"
                )

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".part")
        temporary.write_bytes(output)
        os.replace(temporary, destination)
        extracted = 0
        warning = None
        if kind == "asset" and extract_assets:
            target = output_root / category
            result = extract_asset_bundle(
                destination,
                target,
                bundle_key,
                texture_subdirectory="textures" if category == "model" else None,
                textures_only=category == "model",
            )
            extracted = len(result.outputs)
            warning = result.warning
        elif (
            kind == "resource"
            and category == "video"
            and convert_videos
            and decrypt_resources
            and destination.suffix.lower() == ".usm"
        ):
            result = convert_usm_to_mp4(
                destination,
                output=output_root / category / destination.with_suffix(".mp4").name,
                movie_key=movie_key,
                overwrite=overwrite,
                delete_source=remove_usm,
            )
            extracted = 1 if result.output else 0
            warning = result.warning
        elif (
            kind == "resource"
            and category in {"voice", "bgm", "se", "audio"}
            and extract_assets
            and decrypt_resources
            and destination.suffix.lower() in {".acb", ".awb"}
        ):
            result = extract_cri_audio(
                destination,
                output_root=output_root / category,
                overwrite=overwrite,
            )
            extracted = len(result.outputs)
            warning = result.warning
        return DownloadResult(
            kind,
            item.name,
            category,
            "downloaded",
            destination,
            extracted=extracted,
            warning=warning,
        )
    except Exception as exc:
        return DownloadResult(kind, item.name, category, "failed", error=str(exc))


def _selected(
    items,
    kind: str,
    pattern: re.Pattern[str] | None,
    limit: int | None,
    language: str,
    categories: set[str] | None,
):
    selected = [
        item
        for item in items
        if (pattern is None or pattern.search(item.name))
        and language_matches(item.name, language)
        and (categories is None or classify_name(item.name, kind) in categories)
    ]
    return selected if limit is None else selected[:limit]


def _build_jobs(
    database: octodb_pb2.Database,
    kind: str,
    match: str | None,
    limit: int | None,
    language: str,
    categories: str | list[str] | None,
) -> list[tuple[octodb_pb2.Data, str]]:
    pattern = re.compile(match, re.IGNORECASE) if match else None
    selected_categories = parse_categories(categories)
    jobs: list[tuple[octodb_pb2.Data, str]] = []
    if kind in ("all", "asset"):
        jobs.extend(
            (item, "asset")
            for item in _selected(
                database.assetBundleList,
                "asset",
                pattern,
                limit,
                language,
                selected_categories,
            )
        )
    if kind in ("all", "resource"):
        jobs.extend(
            (item, "resource")
            for item in _selected(
                database.resourceList,
                "resource",
                pattern,
                limit,
                language,
                selected_categories,
            )
        )
    return jobs


def count_database_jobs(
    database: octodb_pb2.Database,
    *,
    kind: str = "all",
    match: str | None = None,
    limit: int | None = None,
    language: str = "all",
    categories: str | list[str] | None = None,
) -> int:
    """Return the exact number of filtered download/extraction jobs."""
    return len(_build_jobs(database, kind, match, limit, language, categories))


def download_database(
    database: octodb_pb2.Database,
    output_root: str | Path,
    bundle_cache_root: str | Path | None = None,
    resource_cache_root: str | Path | None = None,
    kind: str = "all",
    workers: int = 12,
    match: str | None = None,
    limit: int | None = None,
    timeout: float = 60.0,
    overwrite: bool = False,
    deobfuscate: bool = True,
    decrypt_resources: bool = True,
    extract_assets: bool = False,
    bundle_key: str | bytes | None = None,
    language: str = "all",
    categories: str | list[str] | None = None,
    convert_videos: bool = False,
    movie_key: str | int | None = None,
    remove_usm: bool = False,
):
    parsed_bundle_key = (
        bundle_key if isinstance(bundle_key, bytes) else parse_bundle_key(bundle_key)
    )
    parsed_movie_key = parse_movie_key(movie_key)
    jobs = _build_jobs(database, kind, match, limit, language, categories)

    output_root = Path(output_root)
    bundle_cache_root = (
        Path(bundle_cache_root) if bundle_cache_root is not None else output_root / "bundles"
    )
    resource_cache_root = (
        Path(resource_cache_root)
        if resource_cache_root is not None
        else bundle_cache_root.parent / "resources"
    )
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [
            executor.submit(
                _download_one,
                item,
                item_kind,
                database.urlFormat,
                output_root,
                bundle_cache_root,
                resource_cache_root,
                timeout,
                overwrite,
                deobfuscate,
                decrypt_resources,
                extract_assets,
                parsed_bundle_key,
                convert_videos,
                parsed_movie_key,
                remove_usm,
            )
            for item, item_kind in jobs
        ]
        for future in as_completed(futures):
            yield future.result()
