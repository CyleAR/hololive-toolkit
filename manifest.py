from __future__ import annotations

import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

import octodb_pb2
from crypto_utils import decrypt_octocache


def load_database(cache_path: str | Path) -> octodb_pb2.Database:
    cache_path = Path(cache_path)
    payload = decrypt_octocache(cache_path.read_bytes())
    database = octodb_pb2.Database()
    database.ParseFromString(payload)
    if not database.urlFormat.startswith(("https://", "http://")):
        raise ValueError(f"Invalid Octo URL format: {database.urlFormat!r}")
    return database


def database_summary(database: octodb_pb2.Database) -> dict[str, object]:
    return {
        "revisionId": database.revisionId,
        "serverTime": database.serverTime,
        "urlFormat": database.urlFormat,
        "assetBundles": len(database.assetBundleList),
        "resources": len(database.resourceList),
    }


def write_manifest_json(database: octodb_pb2.Database, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = MessageToDict(
        database,
        preserving_proto_field_name=True,
        use_integers_for_enums=True,
    )
    output_path.write_text(
        json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
    )
