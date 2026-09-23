from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
import traceback
import uuid
import webbrowser
from pathlib import Path
from time import sleep

from flask import Flask, jsonify, render_template, request, send_file

from transcriber import LocalWhisperTranscriber, MEDIA_EXTENSIONS, PRESETS

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE = BASE_DIR / "workspace"
JOBS_DIR = WORKSPACE / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = None

jobs: dict[str, dict] = {}
download_paths: dict[str, list[Path]] = {}
jobs_lock = threading.Lock()
gpu_slot = threading.Semaphore(1)
WINDOWS_DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def update_job(job_id: str, **values) -> None:
    with jobs_lock:
        jobs[job_id].update(values)


def append_log(job_id: str, message: str) -> None:
    with jobs_lock:
        jobs[job_id].setdefault("log", []).append(message)
        jobs[job_id]["log"] = jobs[job_id]["log"][-200:]


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
            completed: list[Path] = []
            for index, source in enumerate(input_files):
                base = index / total
                span = 1 / total

                def on_progress(frac: float, msg: str) -> None:
                    overall = min(0.99, base + frac * span)
                    update_job(job_id, progress=overall, message=msg)

                completed.append(tx.transcribe_one(source, output_dir, progress=on_progress))

            with jobs_lock:
                download_paths[job_id] = completed
                jobs[job_id].update(
                    status="done",
                    progress=1.0,
                    message="Transcription complete",
                    downloads=[
                        {"name": path.name, "url": f"/download/{job_id}/{index}"}
                        for index, path in enumerate(completed)
                    ],
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
    for upload in uploads:
        if not upload.filename:
            continue
        name = Path(upload.filename.replace("\\", "/")).name
        invalid = (
            not name
            or name in {".", ".."}
            or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name)
            or name.rstrip(" .") != name
            or name.split(".")[0].upper() in WINDOWS_DEVICE_NAMES
            or Path(name).suffix.lower() not in MEDIA_EXTENSIONS
        )
        if invalid:
            shutil.rmtree(job_dir, ignore_errors=True)
            return jsonify({"error": f"Invalid recording filename: {name}"}), 400
        destination = input_dir / str(len(saved) + 1) / name
        destination.parent.mkdir(parents=True, exist_ok=True)
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


@app.get("/download/<job_id>/<int:index>")
def download_job(job_id: str, index: int):
    with jobs_lock:
        job = jobs.get(job_id)
        paths = download_paths.get(job_id, [])
        if not job or job["status"] != "done" or index >= len(paths):
            return jsonify({"error": "SRT is not ready."}), 404
        path = paths[index]
    if not path.is_file() or path.suffix.lower() != ".srt":
        return jsonify({"error": "SRT is not available."}), 404
    return send_file(path, as_attachment=True, download_name=path.name, mimetype="application/x-subrip")


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
