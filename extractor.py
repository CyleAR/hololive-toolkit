from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class ExtractionResult:
    outputs: tuple[Path, ...] = ()
    warning: str | None = None


def parse_bundle_key(value: str | None) -> bytes | None:
    if not value:
        return None
    value = value.strip()
    if len(value) == 32:
        try:
            return bytes.fromhex(value)
        except ValueError:
            pass
    try:
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) == 16:
            return decoded
    except ValueError:
        pass
    encoded = value.encode("utf-8")
    if len(encoded) != 16:
        raise ValueError("Bundle key must be 16 UTF-8 bytes, 32 hex digits, or base64")
    return encoded


def _safe_name(value: str, fallback: str) -> str:
    value = _INVALID_FILENAME.sub("_", value).strip(" .")
    return value or fallback


def _unique_path(directory: Path, stem: str, suffix: str, path_id: int) -> Path:
    candidate = directory / f"{_safe_name(stem, str(path_id))}{suffix}"
    if candidate.exists():
        candidate = directory / f"{_safe_name(stem, str(path_id))}_{path_id}{suffix}"
    return candidate


class _TypeTreeTexture:
    """Minimal Texture2D interface backed by an embedded Unity TypeTree."""

    def __init__(self, obj, tree: dict):
        from UnityPy.enums import TextureFormat

        self.assets_file = obj.assets_file
        self.path_id = obj.path_id
        self.version = obj.version
        self.platform = obj.platform
        self.m_Name = tree.get("m_Name", f"Texture2D_{obj.path_id}")
        for field in (
            "m_Width",
            "m_Height",
            "m_CompleteImageSize",
            "m_MipsStripped",
            "m_MipCount",
            "m_ImageCount",
            "m_TextureDimension",
        ):
            if field in tree:
                setattr(self, field, tree[field])
        self.m_TextureFormat = TextureFormat(tree["m_TextureFormat"])
        inline_data = tree.get("image data", tree.get("m_ImageData", b""))
        self._image_data = bytes(inline_data)
        self.m_StreamData = SimpleNamespace(**tree.get("m_StreamData", {}))

    @property
    def image_data(self):
        if not self._image_data and getattr(self.m_StreamData, "path", ""):
            from UnityPy.helpers.ResourceReader import get_resource_data

            self._image_data = get_resource_data(
                self.m_StreamData.path,
                self.assets_file,
                self.m_StreamData.offset,
                self.m_StreamData.size,
            )
        return self._image_data

    @property
    def image(self):
        from UnityPy.export.Texture2DConverter import get_image_from_texture2d

        return get_image_from_texture2d(self)


def _repair_texture_from_typetree(obj, data):
    """Repair Unity 6 Texture2D fields that older UnityPy layouts misalign."""
    if tuple(getattr(obj, "version", ())) < (6000,):
        return data

    tree = obj.read_typetree()
    if not isinstance(tree, dict):
        return data

    # When the shifted value is not a valid TextureFormat, UnityPy abandons
    # its generated class and returns a NodeHelper. Build the small interface
    # required by its texture converter directly from the authoritative tree.
    if not hasattr(data, "image"):
        return _TypeTreeTexture(obj, tree)

    scalar_fields = (
        "m_Width",
        "m_Height",
        "m_CompleteImageSize",
        "m_MipsStripped",
        "m_MipCount",
        "m_ImageCount",
        "m_TextureDimension",
    )
    for field in scalar_fields:
        if field in tree:
            setattr(data, field, tree[field])

    if "m_TextureFormat" in tree:
        from UnityPy.enums import TextureFormat

        data.m_TextureFormat = TextureFormat(tree["m_TextureFormat"])

    stream_tree = tree.get("m_StreamData")
    if isinstance(stream_tree, dict):
        stream = getattr(data, "m_StreamData", None)
        if stream is not None:
            for field in ("path", "offset", "size"):
                if field in stream_tree:
                    setattr(stream, field, stream_tree[field])
    return data


def extract_asset_bundle(
    bundle_path: str | Path,
    destination: str | Path,
    bundle_key: bytes | None = None,
    unity_version: str = "6000.3.15f1",
) -> ExtractionResult:
    """Export common Unity payloads. Encrypted bundles require a 16-byte key."""
    try:
        import UnityPy
    except ImportError:
        return ExtractionResult(warning="UnityPy is not installed")

    try:
        UnityPy.config.FALLBACK_UNITY_VERSION = unity_version
        if bundle_key is not None:
            UnityPy.set_assetbundle_decrypt_key(bundle_key)
        environment = UnityPy.load(str(bundle_path))
        destination = Path(destination)
        outputs: list[Path] = []
        warnings: list[str] = []

        objects = list(environment.objects)

        # UnityPy 1.10.x knows the Unity 6 version number, but its generated
        # Texture2D class still expects fields removed in Unity 6.3.  The
        # embedded TypeTree has the authoritative layout, so hydrate each
        # texture from it and make Sprite pointers reuse the repaired object.
        repaired_textures = {}
        for texture_obj in objects:
            if texture_obj.type.name != "Texture2D":
                continue
            try:
                if tuple(getattr(texture_obj, "version", ())) >= (6000,):
                    # Do not invoke UnityPy's stale generated Texture2D parser:
                    # some shifted values make it fail before we can repair it.
                    texture_data = _repair_texture_from_typetree(texture_obj, None)
                else:
                    texture_data = texture_obj.read()
                repaired_textures[texture_obj.path_id] = texture_data
                texture_obj.read = (
                    lambda return_typetree_on_error=True, _data=texture_data: _data
                )
            except Exception:
                # Preserve the normal per-object warning/reporting path below.
                pass

        for obj in objects:
            type_name = obj.type.name
            if type_name not in {
                "Texture2D",
                "Sprite",
                "TextAsset",
                "AudioClip",
                "MonoBehaviour",
            }:
                continue
            try:
                data = repaired_textures.get(obj.path_id) or obj.read()
                name = getattr(data, "m_Name", None) or getattr(data, "name", None)
                name = str(name or f"{type_name}_{obj.path_id}")

                if type_name in {"Texture2D", "Sprite"}:
                    directory = destination
                    directory.mkdir(parents=True, exist_ok=True)
                    output = _unique_path(directory, name, ".png", obj.path_id)
                    try:
                        data.image.save(output)
                        outputs.append(output)
                    except Exception as image_error:
                        stream = getattr(data, "m_StreamData", None)
                        metadata = {
                            "name": name,
                            "path_id": obj.path_id,
                            "type": type_name,
                            "width": getattr(data, "m_Width", None),
                            "height": getattr(data, "m_Height", None),
                            "format": str(getattr(data, "m_TextureFormat", "")),
                            "stream_path": getattr(stream, "path", None),
                            "stream_offset": getattr(stream, "offset", None),
                            "stream_size": getattr(stream, "size", None),
                            "error": str(image_error),
                        }
                        metadata_output = _unique_path(
                            directory, name, ".texture.json", obj.path_id
                        )
                        metadata_output.write_text(
                            json.dumps(metadata, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        outputs.append(metadata_output)
                        warnings.append(f"{name}: {image_error}")
                elif type_name == "TextAsset":
                    payload = getattr(data, "m_Script", getattr(data, "script", b""))
                    if isinstance(payload, str):
                        payload = payload.encode("utf-8")
                    directory = destination
                    directory.mkdir(parents=True, exist_ok=True)
                    output = _unique_path(directory, name, ".txt", obj.path_id)
                    output.write_bytes(bytes(payload))
                    outputs.append(output)
                elif type_name == "MonoBehaviour":
                    directory = destination
                    directory.mkdir(parents=True, exist_ok=True)
                    output = _unique_path(directory, name, ".json", obj.path_id)
                    tree = obj.read_typetree()
                    output.write_text(
                        json.dumps(tree, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )
                    outputs.append(output)
                elif type_name == "AudioClip":
                    directory = destination
                    directory.mkdir(parents=True, exist_ok=True)
                    for sample_name, payload in data.samples.items():
                        suffix = Path(sample_name).suffix or ".wav"
                        stem = Path(sample_name).stem or name
                        output = _unique_path(directory, stem, suffix, obj.path_id)
                        output.write_bytes(payload)
                        outputs.append(output)
            except Exception as object_error:
                warnings.append(f"{type_name}/{obj.path_id}: {object_error}")

        if not outputs:
            warning = "; ".join(warnings) or "Bundle opened but no supported objects were found"
            return ExtractionResult(warning=warning)
        return ExtractionResult(tuple(outputs), "; ".join(warnings) or None)
    except Exception as exc:
        message = str(exc)
        if "encrypted" in message.lower() and bundle_key is None:
            message = "Unity bundle is encrypted; supply --bundle-key to export objects"
        return ExtractionResult(warning=message)
