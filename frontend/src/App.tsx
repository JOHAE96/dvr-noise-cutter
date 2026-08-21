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
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = useCallback(async (files: File[], params: JobParams) => {
    setSubmitting(true);
    setSubmitError(null);
    setUploadProgress(0);
    try {
      const { job_id } = await createJob(files, params, setUploadProgress);
      sessionStorage.setItem(JOB_ID_KEY, job_id);
      setJobId(job_id);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
      setUploadProgress(null);
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
        <>
          <img src="/explaination.jpeg" alt="Analog video noise segments get detected and cut out" className="explanation-image" />
          <UploadForm
            onSubmit={handleSubmit}
            submitting={submitting}
            uploadProgress={uploadProgress}
            error={submitError}
          />
        </>
      )}
    </main>
  );
}
