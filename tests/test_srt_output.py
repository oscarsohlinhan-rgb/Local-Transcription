from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import transcriber
import webapp


class SrtOutputTests(TestCase):
    def test_transcription_writes_only_srt_with_original_basename(self) -> None:
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            manifest = {
                "source": {"source_name": "My lecture (part 1).mp4", "sha256": "abc"},
                "settings": {"model": "small.en", "device": "cpu", "compute_type": "int8"},
            }
            segments = [{"start": 1.0, "end": 2.5, "text": "Hello world."}]

            result = transcriber.write_outputs(output_dir, manifest, segments, {"language": "en"})

            self.assertEqual(result, output_dir / "My lecture (part 1).srt")
            self.assertEqual([path.name for path in output_dir.iterdir()], ["My lecture (part 1).srt"])
            self.assertIn("00:00:01,000 --> 00:00:02,500", result.read_text(encoding="utf-8"))

    def test_upload_keeps_original_filename(self) -> None:
        with TemporaryDirectory() as directory:
            with patch.object(webapp, "JOBS_DIR", Path(directory)):
                with patch("webapp.threading.Thread"):
                    response = webapp.app.test_client().post(
                        "/api/jobs",
                        data={"files": (BytesIO(b"media"), "My lecture (part 1).mp4")},
                        content_type="multipart/form-data",
                    )

                self.assertEqual(response.status_code, 200)
                job = response.get_json()
                self.assertEqual(job["files"], ["My lecture (part 1).mp4"])
                saved = list((Path(directory) / job["id"] / "inputs").rglob("*.mp4"))
                self.assertEqual([path.name for path in saved], ["My lecture (part 1).mp4"])
                webapp.jobs.pop(job["id"], None)

    def test_completed_batch_offers_each_srt_directly(self) -> None:
        class FakeTranscriber:
            def __init__(self, **_kwargs):
                pass

            def transcribe_one(self, source: Path, output_dir: Path, progress):
                result = output_dir / f"{source.stem}.srt"
                result.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
                progress(1.0, "Done")
                return result

        with TemporaryDirectory() as directory:
            sources = [Path(directory) / "Lab_Video_4.1.mp4", Path(directory) / "Lab_Video_4.2.mp4"]
            for source in sources:
                source.write_bytes(b"media")
            job_id = "testjob"
            webapp.jobs[job_id] = {"id": job_id, "status": "queued", "progress": 0.0, "log": []}

            with patch.object(webapp, "JOBS_DIR", Path(directory)):
                with patch.object(webapp, "LocalWhisperTranscriber", FakeTranscriber):
                    webapp.run_job(job_id, sources, "fast", "cpu", "en", "")
                job = webapp.jobs[job_id]
                self.assertEqual(job["status"], "done")
                self.assertEqual(
                    [item["name"] for item in job["downloads"]],
                    ["Lab_Video_4.1.srt", "Lab_Video_4.2.srt"],
                )
                self.assertFalse(list((Path(directory) / job_id).rglob("*.zip")))
                response = webapp.app.test_client().get(job["downloads"][0]["url"])
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("Lab_Video_4.1.srt", response.headers["Content-Disposition"])
                finally:
                    response.close()

            webapp.jobs.pop(job_id, None)
            webapp.download_paths.pop(job_id, None)
