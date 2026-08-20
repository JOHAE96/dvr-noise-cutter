import type { NoiseSegment } from "../types";

export function SegmentsTable({ segments }: { segments: NoiseSegment[] }) {
  if (segments.length === 0) {
    return <p className="info-message">Kein Rauschen erkannt.</p>;
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Start (s)</th>
          <th>Ende (s)</th>
          <th>Dauer (s)</th>
        </tr>
      </thead>
      <tbody>
        {segments.map((seg, i) => (
          <tr key={i}>
            <td>{i + 1}</td>
            <td>{seg.start_sec.toFixed(2)}</td>
            <td>{seg.end_sec.toFixed(2)}</td>
            <td>{seg.duration_sec.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
