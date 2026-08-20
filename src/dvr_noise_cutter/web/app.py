"""FastAPI app: upload a video (or several), poll job status, download results.

No auth here — access control is Traefik's basicauth middleware in front of
this stack (see docker-compose.yml). No CORS setup either — the frontend is
always served same-origin (Vite dev proxy locally, nginx /api/ proxy in prod).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from dvr_noise_cutter.web.jobs import Job, has_allowed_suffix, run_job, sanitize_filename, store
from dvr_noise_cutter.web.schemas import Operation, job_to_response
from dvr_noise_cutter.web.ttl import sweep_loop

JOBS_DIR = Path(os.environ.get("DVR_JOBS_DIR", str(Path.cwd() / "data" / "jobs")))
JOB_TTL_HOURS = float(os.environ.get("JOB_TTL_HOURS", "24"))

JOBS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    sweep_task = asyncio.create_task(sweep_loop(JOBS_DIR, JOB_TTL_HOURS, store))
    yield
    sweep_task.cancel()


app = FastAPI(title="DVR Noise Cutter", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.post("/api/jobs", status_code=202)
async def create_job(
    files: list[UploadFile] = File(...),
    operation: Operation = Form(...),
    threshold: float = Form(0.5),
    min_segment_duration: float = Form(1.0),
    sample_rate: int = Form(5),
    min_clip_duration: float = Form(3.0),
    preview: bool = Form(False),
) -> dict:
    if not files:
        raise HTTPException(400, "No files uploaded.")

    for f in files:
        if not has_allowed_suffix(f.filename or ""):
            raise HTTPException(400, f"Unsupported file type: {f.filename!r} (expected a common video format)")

    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    input_filenames: list[str] = []
    seen: set[str] = set()
    for f in files:
        name = sanitize_filename(f.filename or "video.mp4")
        base, suffix = Path(name).stem, Path(name).suffix
        candidate = name
        n = 1
        while candidate in seen:
            candidate = f"{base}_{n}{suffix}"
            n += 1
        seen.add(candidate)
        input_filenames.append(candidate)

        dest = input_dir / candidate
        with dest.open("wb") as out:
            await asyncio.to_thread(shutil.copyfileobj, f.file, out)

    job = Job(
        id=job_id,
        operation=operation.value,
        is_batch=len(files) > 1,
        input_filenames=input_filenames,
        params={
            "threshold": threshold,
            "min_segment_duration": min_segment_duration,
            "sample_rate": sample_rate,
            "min_clip_duration": min_clip_duration,
            "preview": preview,
        },
        dir=job_dir,
    )
    store.create(job)

    asyncio.create_task(asyncio.to_thread(run_job, job_id))

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job_to_response(job)


@app.get("/api/jobs/{job_id}/preview.png")
async def get_preview(job_id: str) -> FileResponse:
    job = store.get(job_id)
    if job is None or not job.has_preview:
        raise HTTPException(404, "Preview not available")
    path = job.dir / "output" / "preview.png"
    if not path.exists():
        raise HTTPException(404, "Preview not available")
    return FileResponse(path, media_type="image/png")


@app.get("/api/jobs/{job_id}/download/{filename}")
async def download_file(job_id: str, filename: str) -> FileResponse:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if filename not in job.output_files:
        raise HTTPException(404, "File not found")

    path = (job.dir / "output" / filename).resolve()
    if not path.is_relative_to(job.dir.resolve()) or not path.exists():
        raise HTTPException(404, "File not found")

    return FileResponse(path, filename=filename)
