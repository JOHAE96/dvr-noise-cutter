import type { BatchFileResult } from "../types";

const STATUS_LABELS: Record<BatchFileResult["status"], string> = {
  ok: "OK",
  skipped: "Übersprungen",
  error: "Fehler",
};

export function BatchResultsTable({ results }: { results: BatchFileResult[] }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Datei</th>
          <th>Status</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        {results.map((r) => (
          <tr key={r.filename} className={`status-${r.status}`}>
            <td>{r.filename}</td>
            <td>{STATUS_LABELS[r.status]}</td>
            <td>{r.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
