"""Request/response shapes for the web API."""

from __future__ import annotations

from dataclasses import asdict
from enum import Enum

from dvr_noise_cutter.web.jobs import Job


class Operation(str, Enum):
    analyze = "analyze"
    cut = "cut"
    split = "split"


def job_to_response(job: Job) -> dict:
    return {
        "id": job.id,
        "operation": job.operation,
        "is_batch": job.is_batch,
        "status": job.status,
        "phase": job.phase,
        "progress": job.progress,
        "current_file": job.current_file,
        "error": job.error,
        "message": job.message,
        "input_filenames": job.input_filenames,
        "created_at": job.created_at,
        "segments": job.segments,
        "batch_results": [asdict(r) for r in job.batch_results] if job.batch_results is not None else None,
        "has_preview": job.has_preview,
        "output_files": job.output_files,
    }
