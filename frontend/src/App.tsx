import { useCallback, useState } from "react";
import "./App.css";
import { createJob } from "./api";
import { JobStatus } from "./components/JobStatus";
import { UploadForm } from "./components/UploadForm";
import type { JobParams } from "./types";

const JOB_ID_KEY = "dvrCutterJobId";

export default function App() {
  const [jobId, setJobId] = useState<string | null>(() => sessionStorage.getItem(JOB_ID_KEY));
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = useCallback(async (files: File[], params: JobParams) => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const { job_id } = await createJob(files, params);
      sessionStorage.setItem(JOB_ID_KEY, job_id);
      setJobId(job_id);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }, []);

  const handleReset = useCallback(() => {
    sessionStorage.removeItem(JOB_ID_KEY);
    setJobId(null);
  }, []);

  return (
    <main className="app">
      <h1>FPV DVR Noise Cutter</h1>
      {jobId ? (
        <JobStatus jobId={jobId} onReset={handleReset} />
      ) : (
        <UploadForm onSubmit={handleSubmit} submitting={submitting} error={submitError} />
      )}
    </main>
  );
}
