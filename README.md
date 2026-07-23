# HololiveToolkit/hololive Dreams

A toolkit for `hololive Dreams`.

## Important Notice

***As a courtesy to other fans, please refrain from spoiling unreleased content
if any is found after decrypting the game data.***

## How to use

1. Install the requirements.

   ```powershell
   python -m pip install -r requirements.txt
   ```

   Video conversion also requires `ffmpeg` on `PATH`. Audio conversion uses the
   `cridecoder` Python package installed from `requirements.txt`.

2. Copy `octocacheevai` into the `cache` folder.

   The default Steam location is:

   ```text
   *\steamapps\common\hololiveDreams\octo\pdb\5\400001\octocacheevai
   ```

   The resulting toolkit layout should be:

   ```text
   hololive-toolkit\
   ├─ cache\
   │  └─ octocacheevai
   ├─ main.py
   └─ requirements.txt
   ```

3. Run `main.py`.

   By default, this downloads and extracts every category for Japanese and
   shared data:

   ```powershell
   python main.py
   ```

   Use `--language` to select another language. For example, use `kor` for
   Korean:

   ```powershell
   python main.py --language kor
   ```

   `--cache` and `--output` are optional. By default, the toolkit reads
   `cache/octocacheevai`, caches Unity bundles in `cache/bundles`, caches
   converted media sources in `cache/resources`, and writes only final
   extracted files to `cache/extract`.

## Languages and categories

Supported languages:

```text
jpn, eng, kor, chs, cht, ind, all
```

- `jpn`: Japanese (default)
- `eng`: English
- `kor`: Korean
- `chs`: Simplified Chinese
- `cht`: Traditional Chinese
- `ind`: Indonesian
- `all`: All languages

Supported categories:

```text
img, adv, live2d, model, motion, effect, audio, video, chart, all
```
Omitting `--categories` is the same as `--categories all`. Specify a
comma-separated list only when limiting the download.


`audio` includes voice, BGM, SE, and other ACB/AWB resources. External AWB
files and AWBs embedded in ACB files are decoded to PCM16 WAV automatically.
Non-Japanese
language selections include shared base assets together with the matching
`_lang-*` assets.

## Examples

Inspect the local OCTO database:

```powershell
python main.py --inspect
```

Write the decoded manifest as JSON:

```powershell
python main.py --inspect --json "cache\OctoManifest.json"
```

Extract a small test selection:

```powershell
python main.py --categories img,adv --limit 10 --workers 4
```

Download all categories for all languages:

```powershell
python main.py --language all
```

Download and decrypt without extracting Unity objects or converting media:

```powershell
python main.py --no-extract
```

Download and extract voice, BGM, and sound effects to WAV:

```powershell
python main.py --categories audio
```


Download, decrypt, and convert CRI USM videos to MP4:

```powershell
python main.py --categories video
```

The source `.usm` is removed only after the generated MP4 passes a decode
validation. Hololive Dreams' videos do not require a CRI Movie key;
`--movie-key` is available for compatible encrypted data.

Existing downloads are skipped automatically and can be resumed with the same
command. Use `--overwrite` to download them again.

## Output

Only final extracted files are stored in category folders. Model textures use
a dedicated `textures` subdirectory:

```text
cache\extract\
├─ img\*.png
├─ adv\*.json
├─ live2d\*
├─ model\*
│  └─ textures\*.png
├─ motion\*
├─ effect\*
├─ voice\wav\*.wav
├─ bgm\wav\*.wav
├─ se\wav\*.wav
├─ audio\wav\*.wav
├─ video\*.mp4
└─ chart\*
```

Downloaded Unity bundles are retained once under the shared `cache/bundles`
directory, so repeated downloads and extraction reuse the same files. Use
`--bundle-cache` to choose another location. Only embedded model `Texture2D`
and `Sprite` objects are exported under `cache/extract/model/textures`.


Original ACB/AWB files are retained under `cache/resources` for reuse. Use
`--resource-cache` to choose another location. Single-entry banks produce
`wav/<bank>.wav`; multi-entry banks use `wav/<bank>/<bank>_<id>.wav`.
## Special Thanks

- [vilebbit/HoshimiToolkit](https://github.com/vilebbit/HoshimiToolkit)
- [vilebbit/vision-meta](https://github.com/vilebbit/vision-meta)
