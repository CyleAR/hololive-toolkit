from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import cridecoder


@dataclass(frozen=True)
class AudioExtractionResult:
    outputs: tuple[Path, ...] = ()
    warning: str | None = None


@dataclass(frozen=True)
class _AwbEntry:
    wave_id: int
    payload: bytes
    extension: str


def _read_little(data: bytes, offset: int, size: int) -> int:
    end = offset + size
    if offset < 0 or size <= 0 or end > len(data):
        raise ValueError("AFS2 table extends beyond the file")
    return int.from_bytes(data[offset:end], "little")


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _audio_extension(payload: bytes) -> str:
    if payload.startswith(b"HCA\x00") or payload.startswith(b"EHCA"):
        return ".hca"
    if payload.startswith(b"RIFF"):
        return ".wav"
    if payload.startswith(b"OggS"):
        return ".ogg"
    if payload.startswith(b"\x80\x00"):
        return ".adx"
    return ".bin"


def _parse_afs2(data: bytes, base_offset: int) -> tuple[_AwbEntry, ...]:
    if data[base_offset : base_offset + 4] != b"AFS2":
        raise ValueError("CRI AWB does not start with AFS2")
    if base_offset + 16 > len(data):
        raise ValueError("AFS2 header is truncated")

    offset_size = data[base_offset + 5]
    id_size = data[base_offset + 6]
    file_count = _read_little(data, base_offset + 8, 4)
    alignment = _read_little(data, base_offset + 12, 2) or 1
    if offset_size not in (2, 4, 8) or id_size not in (2, 4, 8):
        raise ValueError(
            f"Unsupported AFS2 table sizes: offset={offset_size}, id={id_size}"
        )
    if file_count > 1_000_000:
        raise ValueError(f"Unreasonable AFS2 entry count: {file_count}")

    ids_offset = base_offset + 16
    offsets_offset = ids_offset + file_count * id_size
    table_end = offsets_offset + (file_count + 1) * offset_size
    if table_end > len(data):
        raise ValueError("AFS2 entry table is truncated")

    entries: list[_AwbEntry] = []
    for index in range(file_count):
        wave_id = _read_little(data, ids_offset + index * id_size, id_size)
        relative_start = _read_little(
            data, offsets_offset + index * offset_size, offset_size
        )
        relative_end = _read_little(
            data, offsets_offset + (index + 1) * offset_size, offset_size
        )
        start = _align(base_offset + relative_start, alignment)
        end = base_offset + relative_end
        if start >= end or end > len(data):
            raise ValueError(
                f"Invalid AFS2 entry {index}: start={start}, end={end}, size={len(data)}"
            )
        payload = data[start:end]
        entries.append(_AwbEntry(wave_id, payload, _audio_extension(payload)))
    return tuple(entries)


def _output_path(
    source: Path, wave_id: int, entry_count: int, output_root: Path | None
) -> Path:
    wav_root = (
        output_root / "wav" if output_root is not None else source.parent / "wav"
    )
    if entry_count == 1:
        return wav_root / f"{source.stem}.wav"
    return wav_root / source.stem / f"{source.stem}_{wave_id:04d}.wav"


def extract_cri_audio(
    source: str | Path,
    *,
    output_root: str | Path | None = None,
    overwrite: bool = False,
) -> AudioExtractionResult:
    """Extract an external AWB or an ACB-embedded AWB and decode entries to WAV."""
    source = Path(source)
    output_root = Path(output_root) if output_root is not None else None
    try:
        data = source.read_bytes()
        if source.suffix.lower() == ".awb":
            base_offset = 0
        elif source.suffix.lower() == ".acb":
            base_offset = data.find(b"AFS2")
            if base_offset < 0:
                return AudioExtractionResult()
        else:
            return AudioExtractionResult()

        try:
            entries = _parse_afs2(data, base_offset)
        except ValueError:
            if source.suffix.lower() == ".acb":
                return AudioExtractionResult()
            raise
        if not entries:
            return AudioExtractionResult()

        outputs: list[Path] = []
        for index, entry in enumerate(entries):
            output = _output_path(
                source, entry.wave_id, len(entries), output_root
            )
            if output.exists() and not overwrite:
                outputs.append(output)
                continue

            if entry.extension == ".hca":
                wav_data = cridecoder.decode_hca_bytes(entry.payload)
            elif entry.extension == ".wav":
                wav_data = entry.payload
            else:
                raise RuntimeError(
                    f"AWB entry {index} (wave id {entry.wave_id}) uses an "
                    f"unsupported codec: {entry.extension}"
                )
            if not wav_data.startswith(b"RIFF") or wav_data[8:12] != b"WAVE":
                raise RuntimeError(
                    f"AWB entry {index} (wave id {entry.wave_id}) did not decode to WAV"
                )

            output.parent.mkdir(parents=True, exist_ok=True)
            temporary_output = output.with_name(output.stem + ".part" + output.suffix)
            temporary_output.write_bytes(wav_data)
            os.replace(temporary_output, output)
            outputs.append(output)
        return AudioExtractionResult(tuple(outputs))
    except Exception as exc:
        return AudioExtractionResult(warning=str(exc))
