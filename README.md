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

   By default, this downloads and extracts Japanese images and ADV data:

   ```powershell
   python main.py extract --categories img,adv
   ```

   Use `--language` to select another language. For example, use `kor` for
   Korean:

   ```powershell
   python main.py extract --language kor --categories img,adv
   ```

   `--cache` and `--output` are optional. By default, the toolkit reads
   `cache/octocacheevai` and writes extracted files to `cache/extract`.

## Languages and categories

Supported languages:

```text
jpn, eng, kor, chs, cht, ind, all
```

- `jpn`: Japanese (default for `extract`)
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

`audio` includes voice, BGM, SE, and other ACB/AWB resources. Non-Japanese
language selections include shared base assets together with the matching
`_lang-*` assets.

## Examples

Inspect the local OCTO database:

```powershell
python main.py inspect
```

Write the decoded manifest as JSON:

```powershell
python main.py inspect --json "cache\OctoManifest.json"
```

Extract a small test selection:

```powershell
python main.py extract --categories img,adv --limit 10 --workers 4
```

Extract all known categories:

```powershell
python main.py extract --categories all
```

Existing downloads are skipped automatically and can be resumed with the same
command. Use `--overwrite` to download them again.

## Output

Extracted files are stored in flat category folders without per-bundle or
per-object-type subdirectories:

```text
cache\extract\
├─ img\*.png
├─ adv\*.json
├─ live2d\*
├─ model\*
├─ motion\*
├─ effect\*
├─ voice\*
├─ bgm\*
├─ se\*
├─ video\*
└─ chart\*
```

Downloaded Unity bundles are retained separately under `cache/extract/bundles`
so extraction can be resumed without downloading them again.

## Special Thanks

- [vilebbit/HoshimiToolkit](https://github.com/vilebbit/HoshimiToolkit)
- [vilebbit/vision-meta](https://github.com/vilebbit/vision-meta)
