import { useEffect, useRef, useState } from "react";
import { getJob, previewUrl } from "../api";
import type { JobResponse } from "../types";
import { BatchResultsTable } from "./BatchResultsTable";
import { DownloadLinks } from "./DownloadLinks";
import { SegmentsTable } from "./SegmentsTable";

const POLL_INTERVAL_MS = 1500;

export function JobStatus({ jobId, onReset }: { jobId: string; onReset: () => void }) {
  const [job, setJob] = useState<JobResponse | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await getJob(jobId);
        if (cancelled) return;
        setJob(data);
        setPollError(null);
        if ((data.status === "done" || data.status === "error") && intervalRef.current !== null) {
          window.clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      } catch (err) {
        if (!cancelled) setPollError(err instanceof Error ? err.message : String(err));
      }
    }

    poll();
    intervalRef.current = window.setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (intervalRef.current !== null) window.clearInterval(intervalRef.current);
    };
  }, [jobId]);

  if (pollError && !job) {
    return (
      <div className="job-status">
        <p className="error-message">{pollError}</p>
        <button onClick={onReset}>Neuer Job</button>
      </div>
    );
  }

  if (!job) {
    return <p>Lade Job-Status…</p>;
  }

  const isActive = job.status === "pending" || job.status === "running";
  const progressPercent = job.progress !== null ? Math.round(job.progress * 100) : null;

  return (
    <div className="job-status">
      <h2>
        {job.is_batch ? `Batch (${job.input_filenames.length} Dateien)` : job.input_filenames[0]} — {job.operation}
      </h2>

      {isActive && (
        <div className="progress-block">
          <div className="progress-bar">
            <div
              className={`progress-fill${progressPercent === null ? " indeterminate" : ""}`}
              style={progressPercent !== null ? { width: `${progressPercent}%` } : undefined}
            />
          </div>
          <p className="progress-label">
            {job.phase}
            {progressPercent !== null ? ` — ${progressPercent}%` : ""}
            {job.is_batch && job.current_file ? ` (${job.current_file})` : ""}
          </p>
        </div>
      )}

      {job.status === "error" && <p className="error-message">Fehler: {job.error}</p>}
      {job.message && <p className="info-message">{job.message}</p>}

      {job.status === "done" && !job.is_batch && job.segments && <SegmentsTable segments={job.segments} />}
      {job.status === "done" && job.is_batch && job.batch_results && (
        <BatchResultsTable results={job.batch_results} />
      )}

      {job.has_preview && (
        <div className="preview-block">
          <h3>Vorschau</h3>
          <img src={previewUrl(job.id)} alt="Score-Kurve" className="preview-image" />
        </div>
      )}

      {job.status === "done" && job.output_files.length > 0 && (
        <DownloadLinks jobId={job.id} filenames={job.output_files} />
      )}

      {(job.status === "done" || job.status === "error") && (
        <button onClick={onReset} className="reset-button">
          Neuer Job
        </button>
      )}
    </div>
  );
}
