import type { JobParams, JobResponse } from "./types";

// fetch() has no upload-progress API, so this uses XMLHttpRequest instead —
// the only way to get real byte-level progress for a large multipart upload.
export function createJob(
  files: File[],
  params: JobParams,
  onProgress?: (fraction: number) => void,
): Promise<{ job_id: string }> {
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

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs");

    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(event.loaded / event.total);
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("Ungültige Antwort vom Server."));
        }
      } else {
        reject(new Error(`Upload fehlgeschlagen (${xhr.status}): ${xhr.responseText}`));
      }
    };

    xhr.onerror = () => reject(new Error("Upload fehlgeschlagen: Netzwerkfehler."));

    xhr.send(form);
  });
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
