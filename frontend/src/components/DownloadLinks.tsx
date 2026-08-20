import { downloadUrl } from "../api";

export function DownloadLinks({ jobId, filenames }: { jobId: string; filenames: string[] }) {
  return (
    <div className="download-links">
      <h3>Download</h3>
      <ul>
        {filenames.map((name) => (
          <li key={name}>
            <a href={downloadUrl(jobId, name)} download>
              {name}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
