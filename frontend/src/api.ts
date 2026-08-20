import type { JobParams, JobResponse } from "./types";

export async function createJob(files: File[], params: JobParams): Promise<{ job_id: string }> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  form.append("operation", params.operation);
  form.append("threshold", String(params.threshold));
  form.append("min_segment_duration", String(params.min_segment_duration));
  form.append("sample_rate", String(params.sample_rate));
  form.append("min_clip_duration", String(params.min_clip_duration));
  form.append("preview", String(params.preview));

  const res = await fetch("/api/jobs", { method: "POST", body: form });
  if (!res.ok) {
    throw new Error(`Upload fehlgeschlagen (${res.status}): ${await res.text()}`);
  }
  return res.json();
}

export async function getJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`/api/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error(`Job-Status konnte nicht geladen werden (${res.status})`);
  }
  return res.json();
}

export function previewUrl(jobId: string): string {
  return `/api/jobs/${jobId}/preview.png`;
}

export function downloadUrl(jobId: string, filename: string): string {
  return `/api/jobs/${jobId}/download/${encodeURIComponent(filename)}`;
}
