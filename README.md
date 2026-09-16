# WhisperFlow Local

A simple **local-first MP4/audio transcription app** built around [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) / CTranslate2.

It is designed for long lecture recordings and preserves the evidence trail:

- originals are never modified;
- source SHA-256 is recorded;
- VAD + word timestamps are enabled;
- optional technical glossary/hotwords;
- NVIDIA CUDA is used when available, with automatic CPU fallback;
- batch upload from the local UI;
- raw ASR stays separate from any later correction;
- outputs include SRT, TXT, Markdown, raw JSON, a low-confidence review queue, and a manifest.

The app is **fully local at transcription time**. The first time you choose a model, Faster-Whisper downloads the model weights from Hugging Face. Once those weights are cached, the same model can be used offline.

## 1. Easiest install

### Windows

1. Install **Python 3.11 or 3.12** from python.org if you do not already have it. During install, enable **Add Python to PATH**.
2. Download/clone this repository.
3. Double-click `setup_windows.bat` once.
4. Double-click `run_windows.bat` whenever you want the app.
5. Your browser opens to `http://127.0.0.1:7860`.

### macOS / Linux

```bash
chmod +x setup_mac_linux.sh run_mac_linux.sh
./setup_mac_linux.sh
./run_mac_linux.sh
```

On minimal Linux desktops, Tk is **not** required because the UI runs in your normal web browser.

## 2. How to use the UI

1. Choose one or multiple lecture recordings.
2. Pick a quality preset:
   - **Fast — `small.en`**: lower resource use.
   - **Balanced — `medium.en`**: default for technical English lectures.
   - **Accurate — `large-v3-turbo`**: stronger model, best with a capable GPU.
3. Leave compute on **Auto**. The app tries NVIDIA CUDA first when CTranslate2 can use it, otherwise it runs CPU `int8`.
4. Add module terms in **Technical glossary / hotwords**. Example:

   `MME3252, Wheatstone bridge, transducer, op-amp, instrumentation amplifier, DS18B20`

5. Click **Start local transcription**.
6. Download the ZIP when complete.

The local server binds only to `127.0.0.1` by default, so it is not exposed to other devices on your network.

## 3. Outputs

Each recording gets its own folder named with the source stem + first 10 characters of its SHA-256 hash:

```text
recording-name-abc123def4/
  transcript.srt
  transcript.txt
  transcript.md
  raw_transcript.json
  review_queue.csv
  manifest.json
```

### Why both raw JSON and text?

`raw_transcript.json` is the evidence-preserving ASR output with timestamps, word probabilities, and segment diagnostics. `transcript.txt` is just the convenient plain-text view. If you later correct ASR mistakes, keep the corrected transcript as a **new derivative** rather than overwriting the raw evidence.

`review_queue.csv` automatically flags segments with suspicious confidence/compression/no-speech signals. Those flags are triage hints, not proof that a line is wrong.

## 4. Command-line mode for huge folders

The browser UI copies selected recordings into a local job workspace. For a very large folder, CLI mode avoids that extra copy:

```bash
# Windows after setup
.venv\Scripts\python.exe cli.py "D:\Lectures\MME3252" --preset balanced --output "D:\Lectures\Transcripts"

# macOS/Linux after setup
.venv/bin/python cli.py ~/Lectures/MME3252 --preset balanced --output ~/Lectures/Transcripts
```

Recursive folders:

```bash
python cli.py /path/to/lectures --recursive --preset balanced --output /path/to/transcripts
```

Useful options:

```text
--preset fast|balanced|accurate
--device auto|cuda|cpu
--language en
--glossary "Wheatstone bridge, op-amp, DS18B20"
--model <any Faster-Whisper model name>
```

## 5. NVIDIA GPU notes

Faster-Whisper itself is installed by the setup script. GPU acceleration additionally requires the NVIDIA runtime libraries expected by the installed CTranslate2 version. Current Faster-Whisper documentation specifies **CUDA 12 cuBLAS + cuDNN 9** for the latest CTranslate2 builds.

The app does not make GPU support mandatory: if Auto mode cannot start CUDA, it retries on CPU `int8` and records the fallback reason in `manifest.json`.

If you already have a working Faster-Whisper/CUDA environment, this app should use it automatically.

## 6. Privacy

- No OpenAI API or other transcription API is used.
- The UI server is local-only (`127.0.0.1`).
- Recordings are processed on your machine.
- Uploaded UI copies and outputs live under `workspace/jobs/` and are ignored by Git.
- Delete a finished job folder whenever you no longer need the local copy.

## 7. Brain-compatible reliability choices

This repo intentionally follows the lecture-ingestion workflow used for technical classes:

- preserve source media;
- hash before processing;
- keep timestamped raw evidence immutable;
- use VAD, word timestamps, and technical hotwords;
- create a review queue rather than pretending ASR is perfect;
- treat the original recording as the authoritative source for equations, units, assessment rules, and visually dependent explanations.

## Troubleshooting

### First model load seems slow
The model is downloading once. Later runs reuse the local cache.

### CUDA error
Leave Compute on **Auto**. If CUDA initialization fails, the app falls back to CPU. If you specifically want GPU acceleration, update/install the CUDA/cuDNN runtime expected by your CTranslate2 version.

### Port 7860 is already in use
Run:

```bash
python webapp.py --port 7861
```

### I want absolutely no browser UI
Use `cli.py`; the transcription engine and outputs are the same.
