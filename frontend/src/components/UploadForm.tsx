import { useState, type ChangeEvent, type FormEvent } from "react";
import type { JobParams, Operation } from "../types";

interface UploadFormProps {
  onSubmit: (files: File[], params: JobParams) => void;
  submitting: boolean;
  error: string | null;
}

export function UploadForm({ onSubmit, submitting, error }: UploadFormProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [operation, setOperation] = useState<Operation>("split");
  const [threshold, setThreshold] = useState(0.5);
  const [minSegmentDuration, setMinSegmentDuration] = useState(1.0);
  const [sampleRate, setSampleRate] = useState(5);
  const [minClipDuration, setMinClipDuration] = useState(3.0);
  const [preview, setPreview] = useState(false);

  function handleFilesChange(e: ChangeEvent<HTMLInputElement>) {
    setFiles(e.target.files ? Array.from(e.target.files) : []);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (files.length === 0) return;
    onSubmit(files, {
      operation,
      threshold,
      min_segment_duration: minSegmentDuration,
      sample_rate: sampleRate,
      min_clip_duration: minClipDuration,
      preview,
    });
  }

  const isBatch = files.length > 1;

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <div className="field-group file-pickers">
        <label className="file-picker-button">
          Dateien wählen
          <input
            type="file" multiple
            accept=".mp4,.mov,.avi,.mkv,.wmv,.flv,.webm,.m4v,.mpg,.mpeg,.ts,.vob"
            onChange={handleFilesChange}
          />
        </label>
        <label className="file-picker-button">
          Ordner wählen
          <input
            type="file"
            multiple
            // non-standard but widely supported (Chrome/Edge/Firefox/Safari) folder picker
            {...({ webkitdirectory: "" } as Record<string, string>)}
            onChange={handleFilesChange}
          />
        </label>
      </div>

      {files.length > 0 && (
        <p className="file-summary">
          {files.length} Datei{files.length === 1 ? "" : "en"} ausgewählt
          {isBatch ? " — wird als Batch verarbeitet" : ""}
        </p>
      )}

      <label className="field">
        Aktion
        <select value={operation} onChange={(e) => setOperation(e.target.value as Operation)}>
          <option value="analyze">Analysieren</option>
          <option value="cut">Rauschen entfernen (cut)</option>
          <option value="split">In Clips aufteilen (split)</option>
        </select>
      </label>

      <details className="advanced-options">
        <summary>Erweiterte Optionen</summary>
        <div className="field-group">
          <label className="field">
            Threshold
            <input
              type="number" step={0.05} min={0} max={1} value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
            />
          </label>
          <label className="field">
            Min. Rauschdauer (s)
            <input
              type="number" step={0.1} min={0} value={minSegmentDuration}
              onChange={(e) => setMinSegmentDuration(Number(e.target.value))}
            />
          </label>
          <label className="field">
            Sample-Rate (jeder n-te Frame)
            <input
              type="number" step={1} min={1} value={sampleRate}
              onChange={(e) => setSampleRate(Number(e.target.value))}
            />
          </label>
          {operation === "split" && (
            <label className="field">
              Min. Clip-Dauer (s)
              <input
                type="number" step={0.5} min={0} value={minClipDuration}
                onChange={(e) => setMinClipDuration(Number(e.target.value))}
              />
            </label>
          )}
          <label className="field checkbox-field">
            <input type="checkbox" checked={preview} onChange={(e) => setPreview(e.target.checked)} />
            Score-Kurve als Vorschau speichern
          </label>
        </div>
      </details>

      {error && <p className="error-message">{error}</p>}

      <button type="submit" disabled={files.length === 0 || submitting}>
        {submitting ? "Wird hochgeladen…" : "Starten"}
      </button>
    </form>
  );
}
