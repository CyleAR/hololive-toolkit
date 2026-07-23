from __future__ import annotations

import gc
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConversionResult:
    output: Path | None = None
    warning: str | None = None


def validate_mp4(path: str | Path) -> str | None:
    """Return None when FFmpeg can decode the first video frame."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return "FFmpeg was not found on PATH"
    completed = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "null",
            os.devnull,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        return completed.stderr.strip() or "MP4 validation failed"
    return None


def parse_movie_key(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        key = value
    else:
        text = value.strip()
        if not text:
            return None
        key = int(text, 0)
    if not 0 <= key <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("Movie key must be an unsigned 64-bit integer")
    return key


def convert_usm_to_mp4(
    source: str | Path,
    output: str | Path | None = None,
    *,
    movie_key: str | int | None = None,
    overwrite: bool = False,
    delete_source: bool = False,
) -> ConversionResult:
    """Decrypt a CRI USM and remux its first video stream to an MP4."""
    source = Path(source)
    output = Path(output) if output is not None else source.with_suffix(".mp4")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return ConversionResult(warning="FFmpeg was not found on PATH")

    if output.exists() and not overwrite:
        validation_error = validate_mp4(output)
        if validation_error is None:
            if delete_source:
                try:
                    source.unlink(missing_ok=True)
                except OSError as exc:
                    return ConversionResult(
                        output, f"MP4 is valid, but the USM could not be removed: {exc}"
                    )
            return ConversionResult(output)

    try:
        from wannacri.usm import Usm
    except ImportError:
        return ConversionResult(warning="WannaCRI is not installed")

    temporary_output = output.with_name(output.stem + ".part" + output.suffix)
    try:
        key = parse_movie_key(movie_key)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="hololive-usm-", ignore_cleanup_errors=True
        ) as temporary_directory:
            usm = Usm.open(source, key=key)
            videos, audios = usm.demux(
                temporary_directory,
                save_alpha=False,
                folder_name="streams",
            )
            if not videos:
                raise ValueError("USM contains no supported video stream")

            command = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                videos[0],
            ]
            for audio in audios:
                command.extend(("-i", audio))
            command.extend(("-map", "0:v:0"))
            for index in range(len(audios)):
                command.extend(("-map", f"{index + 1}:a:0"))
            command.extend(("-c:v", "copy"))
            if audios:
                command.extend(("-c:a", "aac", "-b:a", "192k"))
            command.extend(("-movflags", "+faststart", str(temporary_output)))

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if completed.returncode:
                error = completed.stderr.strip() or "FFmpeg conversion failed"
                raise RuntimeError(error)

            validation_error = validate_mp4(temporary_output)
            if validation_error is not None:
                raise RuntimeError(validation_error)
            del usm
            gc.collect()

        os.replace(temporary_output, output)
        if delete_source:
            try:
                source.unlink(missing_ok=True)
            except OSError as exc:
                return ConversionResult(
                    output, f"MP4 was created, but the USM could not be removed: {exc}"
                )
        return ConversionResult(output)
    except Exception as exc:
        try:
            temporary_output.unlink(missing_ok=True)
        except OSError:
            pass
        return ConversionResult(warning=str(exc))
