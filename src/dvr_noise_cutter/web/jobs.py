"""In-memory job store and background workers bridging the web API to
detector.py/cutter.py/preview.py — the same functions the CLI calls, just
producing JSON-serializable job state instead of console output.
"""

from __future__ import annotations

import re
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from dvr_noise_cutter.cutter import cut_noise_segments, split_at_noise_segments
from dvr_noise_cutter.detector import (
    DetectorWeights,
    NoiseSegment,
    analyze_video_frames,
    get_video_fps,
    segments_from_scores,
)
from dvr_noise_cutter.preview import save_preview_plot

ALLOWED_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".ts", ".vob"}


def has_allowed_suffix(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_SUFFIXES

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_.-]")


def sanitize_filename(name: str) -> str:
    cleaned = _SANITIZE_RE.sub("_", Path(name).name)
    return cleaned or "video"


def _get_total_frames(video_path: Path) -> int:
    cap = cv2.VideoCapture(str(video_path))
    try:
        return int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        cap.release()


def _segments_to_dicts(segments: list[NoiseSegment]) -> list[dict]:
    return [{"start_sec": s.start_sec, "end_sec": s.end_sec, "duration_sec": s.duration_sec} for s in segments]


@dataclass
class BatchFileResult:
    filename: str
    status: str  # "ok" | "skipped" | "error"
    detail: str
    segments: list[dict] | None = None
    output_files: list[str] = field(default_factory=list)


@dataclass
class Job:
    id: str
    operation: str  # "analyze" | "cut" | "split"
    is_batch: bool = False
    status: str = "pending"  # "pending" | "running" | "done" | "error"
    phase: str = "queued"
    progress: float | None = 0.0
    current_file: str | None = None
    error: str | None = None
    message: str | None = None
    input_filenames: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    segments: list[dict] | None = None
    batch_results: list[BatchFileResult] | None = None
    output_files: list[str] = field(default_factory=list)
    has_preview: bool = False
    created_at: float = field(default_factory=time.time)
    dir: Path | None = field(repr=False, default=None)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in kwargs.items():
                setattr(job, key, value)

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def all_ids(self) -> list[str]:
        with self._lock:
            return list(self._jobs.keys())


store = JobStore()


def run_job(job_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        if job.is_batch:
            _run_batch_job(job_id)
        else:
            _run_single_job(job_id)
    except Exception as exc:
        store.update(job_id, status="error", phase="error", error=str(exc))


def _run_single_job(job_id: str) -> None:
    job = store.get(job_id)
    video_path = job.dir / "input" / job.input_filenames[0]
    stem = Path(job.input_filenames[0]).stem
    output_dir = job.dir / "output"

    try:
        store.update(job_id, status="running", phase="analyzing")

        fps = get_video_fps(video_path)
        sample_rate = job.params["sample_rate"]
        frame_interval_sec = sample_rate / fps
        total_frames = _get_total_frames(video_path)

        last_push = 0.0

        def on_frame_read(raw_index: int) -> None:
            nonlocal last_push
            now = time.monotonic()
            if now - last_push < 0.2:
                return
            last_push = now
            progress = (raw_index / total_frames) if total_frames > 0 else None
            store.update(job_id, progress=progress)

        scores = analyze_video_frames(
            video_path,
            sample_rate=sample_rate,
            weights=DetectorWeights(),
            threshold=job.params["threshold"],
            on_frame_read=on_frame_read,
        )
        segments = segments_from_scores(scores, job.params["min_segment_duration"], frame_interval_sec)
        store.update(job_id, phase="segmenting", progress=1.0, segments=_segments_to_dicts(segments))

        if job.params["preview"]:
            save_preview_plot(scores, segments, job.params["threshold"], output_dir / "preview.png")
            store.update(job_id, has_preview=True)

        if job.operation == "analyze":
            store.update(job_id, status="done", phase="done")
            return

        if job.operation == "cut":
            if not segments:
                store.update(
                    job_id, status="done", phase="done",
                    message="No noise segments detected; nothing to cut.",
                )
                return
            store.update(job_id, phase="cutting")
            out_path = output_dir / f"{stem}_clean.mp4"
            cut_noise_segments(video_path, segments, out_path)
            store.update(job_id, status="done", phase="done", output_files=[out_path.name])
            return

        if job.operation == "split":
            store.update(job_id, phase="splitting")
            clips = split_at_noise_segments(
                video_path, segments, output_dir, stem,
                min_clip_duration_sec=job.params["min_clip_duration"],
            )
            output_files = [c.path.name for c in clips]
            if len(clips) >= 2:
                store.update(job_id, phase="zipping")
                zip_path = output_dir / "all_clips.zip"
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
                    for c in clips:
                        zf.write(c.path, arcname=c.path.name)
                output_files.append(zip_path.name)
            store.update(job_id, status="done", phase="done", output_files=output_files)
            return

    except Exception as exc:
        store.update(job_id, status="error", phase="error", error=str(exc))


def _run_batch_job(job_id: str) -> None:
    job = store.get(job_id)
    store.update(job_id, status="running")
    total = len(job.input_filenames)
    results: list[BatchFileResult] = []

    for i, filename in enumerate(job.input_filenames):
        store.update(job_id, current_file=filename, phase="analyzing", progress=i / total)
        video_path = job.dir / "input" / filename
        stem = Path(filename).stem
        file_output_dir = job.dir / "output" / stem
        file_output_dir.mkdir(parents=True, exist_ok=True)

        try:
            total_frames = _get_total_frames(video_path)
            last_push = 0.0

            def on_frame_read(raw_index: int, _i=i, _total_frames=total_frames) -> None:
                nonlocal last_push
                now = time.monotonic()
                if now - last_push < 0.2:
                    return
                last_push = now
                local_fraction = (raw_index / _total_frames) if _total_frames > 0 else 0.0
                store.update(job_id, progress=(_i + local_fraction) / total)

            fps = get_video_fps(video_path)
            scores = analyze_video_frames(
                video_path,
                sample_rate=job.params["sample_rate"],
                weights=DetectorWeights(),
                threshold=job.params["threshold"],
                on_frame_read=on_frame_read,
            )
            segments = segments_from_scores(
                scores, job.params["min_segment_duration"], job.params["sample_rate"] / fps
            )
            segment_dicts = _segments_to_dicts(segments)

            if job.params["preview"]:
                save_preview_plot(scores, segments, job.params["threshold"], file_output_dir / "preview.png")

            if job.operation == "analyze":
                results.append(BatchFileResult(filename, "ok", f"{len(segments)} segment(s)", segment_dicts))
            elif job.operation == "cut":
                if not segments:
                    results.append(BatchFileResult(filename, "skipped", "no noise detected", segment_dicts))
                else:
                    out_path = file_output_dir / f"{stem}_clean.mp4"
                    cut_noise_segments(video_path, segments, out_path)
                    results.append(BatchFileResult(filename, "ok", "cut", segment_dicts, [out_path.name]))
            elif job.operation == "split":
                clips = split_at_noise_segments(
                    video_path, segments, file_output_dir, stem,
                    min_clip_duration_sec=job.params["min_clip_duration"],
                )
                results.append(
                    BatchFileResult(
                        filename, "ok", f"{len(clips)} clip(s)", segment_dicts, [c.path.name for c in clips]
                    )
                )
        except Exception as exc:
            results.append(BatchFileResult(filename, "error", str(exc)))

        store.update(job_id, batch_results=list(results))

    store.update(job_id, phase="zipping")
    output_dir = job.dir / "output"
    files_to_zip = sorted(p for p in output_dir.rglob("*") if p.is_file())
    zip_path = output_dir / "batch_results.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for p in files_to_zip:
            zf.write(p, arcname=p.relative_to(output_dir))

    store.update(job_id, status="done", phase="done", progress=1.0, output_files=["batch_results.zip"])
