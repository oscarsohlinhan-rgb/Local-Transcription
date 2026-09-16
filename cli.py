from __future__ import annotations

import argparse
from pathlib import Path

from transcriber import LocalWhisperTranscriber, PRESETS, discover_media


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Local MP4/audio transcription with Faster-Whisper.")
    p.add_argument("inputs", nargs="+", help="Media files and/or folders")
    p.add_argument("--preset", choices=PRESETS.keys(), default="balanced")
    p.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    p.add_argument("--language", default="en")
    p.add_argument("--glossary", default="", help="Comma-separated domain terms/hotwords")
    p.add_argument("--model", default=None, help="Optional Faster-Whisper model override")
    p.add_argument("--output", default="transcripts", help="Output directory")
    p.add_argument("--recursive", action="store_true", help="Scan folders recursively")
    return p


def main() -> None:
    args = parser().parse_args()
    media: list[Path] = []
    for raw in args.inputs:
        p = Path(raw).expanduser()
        if p.is_dir():
            media.extend(discover_media(p, recursive=args.recursive))
        elif p.is_file():
            media.append(p)
        else:
            raise SystemExit(f"Input does not exist: {p}")

    unique = []
    seen = set()
    for p in media:
        resolved = str(p.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(p)
    if not unique:
        raise SystemExit("No supported media files found.")

    out = Path(args.output).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    tx = LocalWhisperTranscriber(
        preset=args.preset,
        device=args.device,
        language=args.language,
        glossary=args.glossary,
        model_override=args.model,
        log=print,
    )
    for index, source in enumerate(unique, start=1):
        print(f"\n[{index}/{len(unique)}] {source}")
        result = tx.transcribe_one(
            source,
            out,
            progress=lambda f, m: print(f"  {f * 100:5.1f}%  {m}"),
        )
        print(f"  Output: {result}")


if __name__ == "__main__":
    main()
