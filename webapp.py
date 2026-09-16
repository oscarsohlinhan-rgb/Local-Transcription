from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
import traceback
import uuid
import webbrowser
import zipfile
from pathlib import Path
from time import sleep

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from transcriber import LocalWhisperTranscriber, PRESETS

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE = BASE_DIR / "workspace"
JOBS_DIR = WORKSPACE / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = None

jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()
gpu_slot = threading.Semaphore(1)


def update_job(job_id: str, **values) -> None:
    with jobs_lock:
        jobs[job_id].update(values)


def append_log(job_id: str, message: str) -> None:
    with jobs_lock:
        jobs[job_id].setdefault("log", []).append(message)
        jobs[job_id]["log"] = jobs[job_id]["log"][-200:]


def zip_directory(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for path in source.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(source))


def run_job(job_id: str, input_files: list[Path], preset: str, device: str, language: str, glossary: str) -> None:
    job_dir = JOBS_DIR / job_id
    output_dir = job_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        update_job(job_id, status="waiting", message="Waiting for transcription slot")
        with gpu_slot:
            update_job(job_id, status="running", message="Loading model", progress=0.01)
            tx = LocalWhisperTranscriber(
                preset=preset,
                device=device,
                language=language,
                glossary=glossary,
                log=lambda msg: append_log(job_id, msg),
            )
            total = len(input_files)
            for index, source in enumerate(input_files):
                base = index / total
                span = 1 / total

                def on_progress(frac: float, msg: str) -> None:
                    overall = min(0.99, base + frac * span)
                    update_job(job_id, progress=overall, message=msg)

                tx.transcribe_one(source, output_dir, progress=on_progress)

            zip_path = job_dir / "whisperflow-transcripts.zip"
            zip_directory(output_dir, zip_path)
            update_job(
                job_id,
                status="done",
                progress=1.0,
                message="Transcription complete",
                download=f"/download/{job_id}",
            )
    except Exception as exc:
        append_log(job_id, traceback.format_exc())
        update_job(job_id, status="error", message=str(exc), error=str(exc))


@app.get("/")
def home():
    return render_template("index.html", presets=PRESETS)


@app.post("/api/jobs")
def create_job():
    uploads = request.files.getlist("files")
    if not uploads or all(not f.filename for f in uploads):
        return jsonify({"error": "Choose at least one MP4/audio file."}), 400

    preset = request.form.get("preset", "balanced")
    if preset not in PRESETS:
        return jsonify({"error": "Invalid preset."}), 400
    device = request.form.get("device", "auto")
    if device not in {"auto", "cuda", "cpu"}:
        return jsonify({"error": "Invalid device."}), 400
    language = request.form.get("language", "en").strip() or "en"
    glossary = request.form.get("glossary", "").strip()

    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    input_dir = job_dir / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    used_names: set[str] = set()
    for upload in uploads:
        if not upload.filename:
            continue
        name = secure_filename(Path(upload.filename).name) or "recording.mp4"
        stem, suffix = Path(name).stem, Path(name).suffix
        candidate = name
        counter = 2
        while candidate.lower() in used_names:
            candidate = f"{stem}-{counter}{suffix}"
            counter += 1
        used_names.add(candidate.lower())
        destination = input_dir / candidate
        upload.save(destination)
        saved.append(destination)

    if not saved:
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({"error": "No files were uploaded."}), 400

    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "progress": 0.0,
            "message": f"Queued {len(saved)} file(s)",
            "files": [p.name for p in saved],
            "log": [],
        }

    thread = threading.Thread(
        target=run_job,
        args=(job_id, saved, preset, device, language, glossary),
        daemon=True,
    )
    thread.start()
    return jsonify(jobs[job_id])


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found."}), 404
        return jsonify(job)


@app.get("/download/<job_id>")
def download_job(job_id: str):
    zip_path = JOBS_DIR / job_id / "whisperflow-transcripts.zip"
    if not zip_path.exists():
        return jsonify({"error": "Output is not ready."}), 404
    return send_file(zip_path, as_attachment=True, download_name="whisperflow-transcripts.zip")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7860)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    if not args.no_browser:
        threading.Thread(
            target=lambda: (sleep(1.0), webbrowser.open(f"http://{args.host}:{args.port}")),
            daemon=True,
        ).start()
    print(f"WhisperFlow Local UI: http://{args.host}:{args.port}")
    print("Local-only server. Press Ctrl+C to stop.")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
