export type Operation = "analyze" | "cut" | "split";
export type JobStatus = "pending" | "running" | "done" | "error";

export interface NoiseSegment {
  start_sec: number;
  end_sec: number;
  duration_sec: number;
}

export interface BatchFileResult {
  filename: string;
  status: "ok" | "skipped" | "error";
  detail: string;
  segments: NoiseSegment[] | null;
  output_files: string[];
}

export interface JobResponse {
  id: string;
  operation: Operation;
  is_batch: boolean;
  status: JobStatus;
  phase: string;
  progress: number | null;
  current_file: string | null;
  error: string | null;
  message: string | null;
  input_filenames: string[];
  created_at: number;
  segments: NoiseSegment[] | null;
  batch_results: BatchFileResult[] | null;
  has_preview: boolean;
  output_files: string[];
}

export interface JobParams {
  operation: Operation;
  threshold: number;
  min_segment_duration: number;
  sample_rate: number;
  min_clip_duration: number;
  preview: boolean;
}
