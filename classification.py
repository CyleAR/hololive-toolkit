from __future__ import annotations

import re
from collections.abc import Iterable


LANGUAGES = ("all", "jpn", "eng", "kor", "chs", "cht", "ind")
_LANGUAGE_RE = re.compile(
    r"(?:^|_)lang-(chs|cht|eng|ind|kor)(?=$|[_\-.])", re.IGNORECASE
)

ASSET_CATEGORIES = {
    "img",
    "adv",
    "live2d",
    "model",
    "motion",
    "effect",
    "environment",
    "system",
    "asset-other",
}
RESOURCE_CATEGORIES = {
    "voice",
    "bgm",
    "se",
    "audio",
    "video",
    "chart",
    "config",
    "resource-other",
}
ALL_CATEGORIES = ASSET_CATEGORIES | RESOURCE_CATEGORIES

_ALIASES = {
    "image": {"img"},
    "images": {"img"},
    "models": {"model"},
    "motions": {"motion"},
    "effects": {"effect"},
    "env": {"environment"},
    "charts": {"chart"},
    "movies": {"video"},
    "audio-all": {"voice", "bgm", "se", "audio"},
    "resources": RESOURCE_CATEGORIES,
    "assets": ASSET_CATEGORIES,
}


def language_tag(name: str) -> str | None:
    match = _LANGUAGE_RE.search(name)
    return match.group(1).lower() if match else None


def language_matches(name: str, language: str) -> bool:
    """Include shared base data plus the requested localized variant."""
    language = language.lower()
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    tag = language_tag(name)
    if language == "all":
        return True
    if language == "jpn":
        return tag is None
    return tag is None or tag == language


def classify_name(name: str, kind: str) -> str:
    lowered = name.lower()
    prefix = lowered.split("_", 1)[0]
    suffix = lowered.rsplit(".", 1)[-1] if "." in lowered else ""

    if kind == "asset":
        if prefix == "img":
            return "img"
        if prefix == "adv":
            return "adv"
        if prefix == "live2d":
            return "live2d"
        if prefix in {"mdl", "fbx", "ref"}:
            return "model"
        if prefix == "mot":
            return "motion"
        if prefix == "eff":
            return "effect"
        if prefix in {"env", "map"}:
            return "environment"
        if prefix in {"sys", "debug"}:
            return "system"
        return "asset-other"

    if prefix == "vo":
        return "voice"
    if prefix in {"bgm", "music"}:
        return "bgm"
    if prefix == "se":
        return "se"
    if suffix == "usm" or prefix == "mov":
        return "video"
    if suffix == "sus" or prefix == "chart":
        return "chart"
    if suffix == "acf":
        return "config"
    if suffix in {"acb", "awb"}:
        return "audio"
    return "resource-other"


def parse_categories(value: str | Iterable[str] | None) -> set[str] | None:
    if value is None:
        return None
    raw = value.split(",") if isinstance(value, str) else list(value)
    tokens = {token.strip().lower() for token in raw if token.strip()}
    if not tokens or "all" in tokens:
        return None

    categories: set[str] = set()
    unknown: list[str] = []
    for token in tokens:
        if token == "audio":
            categories.update({"voice", "bgm", "se", "audio"})
        elif token in ALL_CATEGORIES:
            categories.add(token)
        elif token in _ALIASES:
            categories.update(_ALIASES[token])
        else:
            unknown.append(token)
    if unknown:
        raise ValueError(f"Unknown categories: {', '.join(sorted(unknown))}")
    return categories
