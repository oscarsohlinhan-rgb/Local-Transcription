from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import shutil
import socket
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

PRESETS = {
    "fast": {
        "label": "Fast",
        "model": "small.en",
        "beam_size": 1,
        "description": "Fastest practical English preset; good for clear lectures and lower-end CPUs.",
    },
    "balanced": {
        "label": "Balanced",
        "model": "medium.en",
        "beam_size": 5,
        "description": "Default for technical English lectures; better terminology accuracy at moderate speed.",
    },
    "accurate": {
        "label": "Accurate",
        "model": "large-v3-turbo",
        "beam_size": 5,
        "description": "Highest-quality preset here; multilingual and best suited to a capable GPU.",
    },
}


@dataclass
class RuntimeChoice:
    device: str
    compute_type: str
    fallback_reason: Optional[str] = None


@dataclass
class SourceManifest:
    source_name: str
    source_path: str
    size_bytes: int
    sha256: str
    modified_at: str


class TranscriptionCancelled(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_. " else "_" for c in value).strip()
    return cleaned or "recording"


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def source_manifest(path: Path) -> SourceManifest:
    stat = path.stat()
    return SourceManifest(
        source_name=path.name,
        source_path=str(path.resolve()),
        size_bytes=stat.st_size,
        sha256=sha256_file(path),
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    )


def detect_runtime(requested: str = "auto") -> RuntimeChoice:
    requested = (requested or "auto").lower()
    if requested == "cpu":
        return RuntimeChoice("cpu", "int8")

    try:
        import ctranslate2

        cuda_count = ctranslate2.get_cuda_device_count()
    except Exception as exc:  # pragma: no cover - depends on host runtime
        cuda_count = 0
        detection_error = f"CUDA detection failed: {exc}"
    else:
        detection_error = None

    if requested == "cuda":
        if cuda_count > 0:
            return RuntimeChoice("cuda", "float16")
        return RuntimeChoice("cpu", "int8", "CUDA was requested but no usable CUDA device was detected.")

    if cuda_count > 0:
        return RuntimeChoice("cuda", "float16")
    return RuntimeChoice("cpu", "int8", detection_error)


def format_clock(seconds: float, srt: bool = False) -> str:
    seconds = max(0.0, float(seconds))
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    if srt:
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def segment_to_dict(segment) -> dict:
    words = []
    for word in (getattr(segment, "words", None) or []):
        words.append(
            {
                "start": getattr(word, "start", None),
                "end": getattr(word, "end", None),
                "word": getattr(word, "word", ""),
                "probability": getattr(word, "probability", None),
            }
        )
    return {
        "id": getattr(segment, "id", None),
        "seek": getattr(segment, "seek", None),
        "start": float(getattr(segment, "start", 0.0)),
        "end": float(getattr(segment, "end", 0.0)),
        "text": getattr(segment, "text", "").strip(),
        "tokens": list(getattr(segment, "tokens", []) or []),
        "temperature": getattr(segment, "temperature", None),
        "avg_logprob": getattr(segment, "avg_logprob", None),
        "compression_ratio": getattr(segment, "compression_ratio", None),
        "no_speech_prob": getattr(segment, "no_speech_prob", None),
        "words": words,
    }


def review_flags(segment: dict) -> list[str]:
    flags: list[str] = []
    avg_logprob = segment.get("avg_logprob")
    compression_ratio = segment.get("compression_ratio")
    no_speech_prob = segment.get("no_speech_prob")
    text = (segment.get("text") or "").strip()

    if avg_logprob is not None and avg_logprob < -0.75:
        flags.append("low_log_probability")
    if compression_ratio is not None and compression_ratio > 2.4:
        flags.append("high_compression_ratio")
    if no_speech_prob is not None and no_speech_prob > 0.60 and text:
        flags.append("high_no_speech_probability")
    if not text:
        flags.append("empty_text")
    return flags


def write_outputs(
    output_dir: Path,
    manifest: dict,
    segments: list[dict],
    info: dict,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_payload = {
        "manifest": manifest,
        "transcription_info": info,
        "segments": segments,
    }
    (output_dir / "raw_transcript.json").write_text(
        json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    plain = "\n".join(s["text"] for s in segments if s["text"]).strip() + "\n"
    (output_dir / "transcript.txt").write_text(plain, encoding="utf-8")

    with (output_dir / "transcript.srt").open("w", encoding="utf-8") as f:
        index = 1
        for seg in segments:
            if not seg["text"]:
                continue
            f.write(f"{index}\n")
            f.write(f"{format_clock(seg['start'], True)} --> {format_clock(seg['end'], True)}\n")
            f.write(seg["text"] + "\n\n")
            index += 1

    md_lines = [
        f"# Transcript — {manifest['source']['source_name']}",
        "",
        "> Raw ASR evidence. Treat timestamps as the route back to the original recording; do not silently rewrite this file.",
        "",
        "## Processing metadata",
        "",
        f"- SHA-256: `{manifest['source']['sha256']}`",
        f"- Model: `{manifest['settings']['model']}`",
        f"- Device: `{manifest['settings']['device']}` / `{manifest['settings']['compute_type']}`",
        f"- Language: `{info.get('language')}` (probability {info.get('language_probability')})",
        "",
        "## Time-aligned transcript",
        "",
    ]
    for seg in segments:
        if seg["text"]:
            md_lines.append(
                f"**[{format_clock(seg['start'])} → {format_clock(seg['end'])}]** {seg['text']}"
            )
            md_lines.append("")
    (output_dir / "transcript.md").write_text("\n".join(md_lines), encoding="utf-8")

    queue_rows = []
    for seg in segments:
        flags = review_flags(seg)
        if flags:
            queue_rows.append(
                {
                    "start": format_clock(seg["start"]),
                    "end": format_clock(seg["end"]),
                    "flags": ";".join(flags),
                    "avg_logprob": seg.get("avg_logprob"),
                    "compression_ratio": seg.get("compression_ratio"),
                    "no_speech_prob": seg.get("no_speech_prob"),
                    "text": seg.get("text", ""),
                }
            )
    with (output_dir / "review_queue.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "start",
                "end",
                "flags",
                "avg_logprob",
                "compression_ratio",
                "no_speech_prob",
                "text",
            ],
        )
        writer.writeheader()
        writer.writerows(queue_rows)

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class LocalWhisperTranscriber:
    def __init__(
        self,
        preset: str = "balanced",
        device: str = "auto",
        language: str = "en",
        glossary: str = "",
        model_override: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset: {preset}")
        self.preset_name = preset
        self.preset = PRESETS[preset]
        self.language = language or "en"
        self.glossary = glossary.strip()
        self.requested_device = device
        self.runtime = detect_runtime(device)
        self.model_name = model_override or self.preset["model"]
        self.log = log or (lambda _: None)
        self.model = None

    def _load_model(self) -> None:
        if self.model is not None:
            return
        from faster_whisper import WhisperModel

        self.log(
            f"Loading model {self.model_name} on {self.runtime.device} ({self.runtime.compute_type})..."
        )
        try:
            self.model = WhisperModel(
                self.model_name,
                device=self.runtime.device,
                compute_type=self.runtime.compute_type,
            )
        except Exception as exc:
            if self.runtime.device == "cuda" and self.requested_device == "auto":
                self._fallback_to_cpu(f"CUDA initialization failed: {exc}")
            else:
                raise

    def _fallback_to_cpu(self, reason: str) -> None:
        from faster_whisper import WhisperModel

        self.log(f"{reason}. Falling back to CPU int8.")
        self.runtime = RuntimeChoice("cpu", "int8", reason)
        self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")

    @staticmethod
    def _looks_like_cuda_runtime_error(exc: Exception) -> bool:
        text = str(exc).lower()
        markers = (
            "cublas",
            "cudnn",
            "cuda",
            "nvrtc",
            "library",
            "dll",
            "driver version is insufficient",
        )
        return any(marker in text for marker in markers)

    def transcribe_one(
        self,
        source_path: Path,
        output_root: Path,
        progress: Optional[Callable[[float, str], None]] = None,
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> Path:
        source_path = Path(source_path)
        if source_path.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ValueError(f"Unsupported media file: {source_path.name}")
        if not source_path.exists():
            raise FileNotFoundError(source_path)

        self._load_model()
        progress = progress or (lambda _fraction, _message: None)
        cancelled = cancelled or (lambda: False)

        progress(0.01, f"Hashing {source_path.name}")
        src = source_manifest(source_path)
        short_hash = src.sha256[:10]
        output_dir = output_root / f"{safe_name(source_path.stem)}-{short_hash}"
        output_dir.mkdir(parents=True, exist_ok=True)

        started_at = utc_now()
        settings = {
            "preset": self.preset_name,
            "model": self.model_name,
            "requested_device": self.requested_device,
            "device": self.runtime.device,
            "compute_type": self.runtime.compute_type,
            "runtime_fallback_reason": self.runtime.fallback_reason,
            "beam_size": self.preset["beam_size"],
            "language": self.language,
            "vad_filter": True,
            "vad_min_silence_duration_ms": 500,
            "word_timestamps": True,
            "hotwords": self.glossary or None,
        }

        kwargs = dict(
            beam_size=self.preset["beam_size"],
            language=self.language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            word_timestamps=True,
            hotwords=self.glossary or None,
        )
        if self.model_name.startswith("distil-"):
            kwargs["condition_on_previous_text"] = False

        def run_once():
            progress(0.05, f"Transcribing {source_path.name} on {self.runtime.device}")
            segments_gen, info_obj = self.model.transcribe(str(source_path), **kwargs)
            duration = float(getattr(info_obj, "duration", 0.0) or 0.0)
            collected: list[dict] = []
            for segment in segments_gen:
                if cancelled():
                    raise TranscriptionCancelled(f"Cancelled while processing {source_path.name}")
                seg = segment_to_dict(segment)
                collected.append(seg)
                if duration > 0:
                    frac = min(0.98, max(0.05, seg["end"] / duration))
                else:
                    frac = 0.5
                progress(frac, f"{source_path.name}: {format_clock(seg['end'])}")
            return collected, info_obj, duration

        try:
            segments, info_obj, duration = run_once()
        except Exception as exc:
            if (
                self.runtime.device == "cuda"
                and self.requested_device == "auto"
                and self._looks_like_cuda_runtime_error(exc)
            ):
                self._fallback_to_cpu(f"CUDA runtime failed during transcription: {exc}")
                progress(0.05, "GPU runtime unavailable; retrying automatically on CPU")
                segments, info_obj, duration = run_once()
            else:
                raise

        settings["device"] = self.runtime.device
        settings["compute_type"] = self.runtime.compute_type
        settings["runtime_fallback_reason"] = self.runtime.fallback_reason

        info = {
            "language": getattr(info_obj, "language", None),
            "language_probability": getattr(info_obj, "language_probability", None),
            "duration_seconds": duration,
            "duration_after_vad_seconds": getattr(info_obj, "duration_after_vad", None),
            "all_language_probs": getattr(info_obj, "all_language_probs", None),
        }
        manifest = {
            "schema_version": 1,
            "source": asdict(src),
            "settings": settings,
            "processing": {
                "started_at": started_at,
                "completed_at": utc_now(),
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "python": sys.version.split()[0],
            },
            "coverage": {
                "source_duration_seconds": duration,
                "last_transcript_end_seconds": segments[-1]["end"] if segments else 0.0,
                "segment_count": len(segments),
                "note": "Silence/non-speech may be omitted by VAD; use the original recording as the authoritative source.",
            },
        }
        write_outputs(output_dir, manifest, segments, info)
        progress(1.0, f"Finished {source_path.name}")
        return output_dir


def discover_media(folder: Path, recursive: bool = False) -> list[Path]:
    folder = Path(folder)
    iterator: Iterable[Path] = folder.rglob("*") if recursive else folder.glob("*")
    return sorted(p for p in iterator if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS)
