"""Typer CLI: analyze, cut, split, and batch commands for finding/removing DVR noise segments."""

from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Optional

import cv2
import typer
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from dvr_noise_cutter.cutter import (
    cut_noise_segments,
    ffprobe_duration,
    invert_segments,
    split_at_noise_segments,
)
from dvr_noise_cutter.detector import (
    DetectorWeights,
    FrameScore,
    NoiseSegment,
    analyze_video_frames,
    get_video_fps,
    segments_from_scores,
)
from dvr_noise_cutter.preview import save_preview_plot

app = typer.Typer(help="Detect and remove analog-noise segments from FPV DVR recordings.")


def _get_total_frames(video: Path) -> int:
    cap = cv2.VideoCapture(str(video))
    try:
        return int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        cap.release()


def _run_detection(
    video: Path,
    sample_rate: int,
    threshold: float,
    min_segment_duration: float,
    console: Console,
) -> tuple[list[FrameScore], list[NoiseSegment]]:
    fps = get_video_fps(video)
    frame_interval_sec = sample_rate / fps
    total_frames = _get_total_frames(video)

    with Progress(console=console) as progress:
        task = progress.add_task("Analyzing frames...", total=total_frames or None)

        def on_frame_read(raw_index: int) -> None:
            progress.update(task, completed=raw_index + 1)

        scores = analyze_video_frames(
            video,
            sample_rate=sample_rate,
            weights=DetectorWeights(),
            threshold=threshold,
            on_frame_read=on_frame_read,
        )

    segments = segments_from_scores(scores, min_segment_duration, frame_interval_sec)
    return scores, segments


def _render_segments_table(segments: list[NoiseSegment], console: Console) -> None:
    if not segments:
        console.print("[green]No noise segments detected.[/green]")
        return

    table = Table(title="Detected noise segments")
    table.add_column("#", justify="right")
    table.add_column("Start (s)", justify="right")
    table.add_column("End (s)", justify="right")
    table.add_column("Duration (s)", justify="right")
    for i, segment in enumerate(segments, start=1):
        table.add_row(str(i), f"{segment.start_sec:.2f}", f"{segment.end_sec:.2f}", f"{segment.duration_sec:.2f}")
    console.print(table)


def _write_preview(video: Path, scores: list[FrameScore], segments: list[NoiseSegment], threshold: float, console: Console) -> None:
    preview_path = video.with_suffix(".preview.png")
    save_preview_plot(scores, segments, threshold, preview_path)
    console.print(f"Wrote preview plot to {preview_path}")


def _render_clips_table(rows: list[tuple[str, float, float]], console: Console, title: str) -> None:
    if not rows:
        console.print("[yellow]No clips.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("#", justify="right")
    table.add_column("Clip", justify="left")
    table.add_column("Start (s)", justify="right")
    table.add_column("End (s)", justify="right")
    table.add_column("Duration (s)", justify="right")
    for i, (name, start, end) in enumerate(rows, start=1):
        table.add_row(str(i), name, f"{start:.2f}", f"{end:.2f}", f"{end - start:.2f}")
    console.print(table)


@app.command()
def analyze(
    video: Path = typer.Argument(..., exists=True, readable=True, help="Path to the DVR video file (mp4/mov)."),
    threshold: float = typer.Option(0.5, help="Combined noise-score threshold in [0, 1]."),
    min_segment_duration: float = typer.Option(1.0, "--min-segment-duration", help="Minimum noise segment duration in seconds."),
    sample_rate: int = typer.Option(5, "--sample-rate", help="Analyze every Nth frame."),
    json_out: Optional[Path] = typer.Option(None, "--json", help="Write detected segments as JSON to this path."),
    preview: bool = typer.Option(False, "--preview", help="Save a debug plot of the score curve."),
) -> None:
    """Analyze VIDEO and report detected noise segments."""
    console = Console()
    scores, segments = _run_detection(video, sample_rate, threshold, min_segment_duration, console)
    _render_segments_table(segments, console)

    if json_out is not None:
        json_out.write_text(json.dumps([asdict(s) for s in segments], indent=2))
        console.print(f"Wrote {len(segments)} segment(s) to {json_out}")

    if preview:
        _write_preview(video, scores, segments, threshold, console)


@app.command()
def cut(
    video: Path = typer.Argument(..., exists=True, readable=True, help="Path to the DVR video file (mp4/mov)."),
    output: Path = typer.Option(..., "--output", help="Path to write the cleaned video."),
    threshold: float = typer.Option(0.5, help="Combined noise-score threshold in [0, 1]."),
    min_segment_duration: float = typer.Option(1.0, "--min-segment-duration", help="Minimum noise segment duration in seconds."),
    sample_rate: int = typer.Option(5, "--sample-rate", help="Analyze every Nth frame."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only show detected segments, don't write output."),
    preview: bool = typer.Option(False, "--preview", help="Save a debug plot of the score curve."),
) -> None:
    """Detect and remove noise segments from VIDEO, writing the result to OUTPUT."""
    console = Console()
    scores, segments = _run_detection(video, sample_rate, threshold, min_segment_duration, console)
    _render_segments_table(segments, console)

    if preview:
        _write_preview(video, scores, segments, threshold, console)

    if dry_run:
        console.print("[yellow]Dry run: no output written.[/yellow]")
        return

    if not segments:
        console.print("[green]No noise segments detected; nothing to cut.[/green]")
        return

    cut_noise_segments(video, segments, output)
    console.print(f"[green]Wrote cleaned video to {output}[/green]")


@app.command()
def split(
    video: Path = typer.Argument(..., exists=True, readable=True, help="Path to the DVR video file (mp4/mov)."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Directory to write split clips into."),
    threshold: float = typer.Option(0.5, help="Combined noise-score threshold in [0, 1]."),
    min_segment_duration: float = typer.Option(1.0, "--min-segment-duration", help="Minimum noise segment duration in seconds."),
    min_clip_duration: float = typer.Option(3.0, "--min-clip-duration", help="Minimum duration for a resulting clip; shorter fragments between dropouts are discarded."),
    sample_rate: int = typer.Option(5, "--sample-rate", help="Analyze every Nth frame."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only show the resulting clip boundaries, don't write output."),
    preview: bool = typer.Option(False, "--preview", help="Save a debug plot of the score curve."),
) -> None:
    """Split VIDEO into separate clips at noise-segment boundaries (e.g., one clip per battery pack)."""
    console = Console()
    scores, segments = _run_detection(video, sample_rate, threshold, min_segment_duration, console)
    _render_segments_table(segments, console)

    if preview:
        _write_preview(video, scores, segments, threshold, console)

    if dry_run:
        total_duration = ffprobe_duration(video)
        keep_segments = invert_segments(segments, total_duration, min_keep_duration_sec=min_clip_duration)
        rows = [(f"{video.stem}_part{i:03d}.mp4", seg.start_sec, seg.end_sec) for i, seg in enumerate(keep_segments, start=1)]
        _render_clips_table(rows, console, title="Would-be clips (dry run)")
        console.print("[yellow]Dry run: no output written.[/yellow]")
        return

    clips = split_at_noise_segments(video, segments, output_dir, video.stem, min_clip_duration_sec=min_clip_duration)
    rows = [(clip.path.name, clip.start_sec, clip.end_sec) for clip in clips]
    _render_clips_table(rows, console, title="Written clips")
    console.print(f"[green]Wrote {len(clips)} clip(s) to {output_dir}[/green]")


class BatchOperation(str, Enum):
    analyze = "analyze"
    cut = "cut"
    split = "split"


def _expand_video_paths(paths: list[Path]) -> list[Path]:
    """Directories are expanded to their mp4/mov files (non-recursive); files pass through."""
    suffixes = {".mp4", ".mov", ".MP4", ".MOV"}
    expanded: list[Path] = []
    for p in paths:
        if p.is_dir():
            expanded.extend(sorted(f for f in p.iterdir() if f.suffix in suffixes))
        else:
            expanded.append(p)
    return expanded


@app.command()
def batch(
    operation: BatchOperation = typer.Argument(..., help="Operation to run on each video: analyze, cut, or split."),
    videos: list[Path] = typer.Argument(..., exists=True, readable=True, help="Video files, or directories to scan for mp4/mov files."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Directory to write outputs into (cleaned/split videos, JSON exports)."),
    threshold: float = typer.Option(0.5, help="Combined noise-score threshold in [0, 1]."),
    min_segment_duration: float = typer.Option(1.0, "--min-segment-duration", help="Minimum noise segment duration in seconds."),
    min_clip_duration: float = typer.Option(3.0, "--min-clip-duration", help="(split only) Minimum duration for a resulting clip."),
    sample_rate: int = typer.Option(5, "--sample-rate", help="Analyze every Nth frame."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only detect and report, don't write cut/split output."),
    preview: bool = typer.Option(False, "--preview", help="Save a debug plot per video."),
    json_export: bool = typer.Option(False, "--json", help="(analyze only) Also write a <name>.json per video into output-dir."),
) -> None:
    """Run analyze/cut/split over multiple videos, or every mp4/mov file in given directories."""
    console = Console()
    output_dir.mkdir(parents=True, exist_ok=True)
    video_paths = _expand_video_paths(videos)
    if not video_paths:
        console.print("[yellow]No video files found.[/yellow]")
        raise typer.Exit(code=1)

    results: list[tuple[str, str, str]] = []

    for video in video_paths:
        console.rule(video.name)
        try:
            scores, segments = _run_detection(video, sample_rate, threshold, min_segment_duration, console)
            _render_segments_table(segments, console)
            if preview:
                _write_preview(video, scores, segments, threshold, console)

            if operation is BatchOperation.analyze:
                if json_export:
                    (output_dir / f"{video.stem}.json").write_text(json.dumps([asdict(s) for s in segments], indent=2))
                results.append((video.name, "ok", f"{len(segments)} segment(s)"))

            elif operation is BatchOperation.cut:
                if dry_run:
                    results.append((video.name, "dry-run", f"{len(segments)} segment(s) would be removed"))
                elif not segments:
                    results.append((video.name, "skipped", "no noise detected"))
                else:
                    out_path = output_dir / f"{video.stem}_clean.mp4"
                    cut_noise_segments(video, segments, out_path)
                    results.append((video.name, "ok", str(out_path)))

            elif operation is BatchOperation.split:
                if dry_run:
                    results.append((video.name, "dry-run", f"{len(segments)} noise segment(s) detected"))
                else:
                    clips = split_at_noise_segments(video, segments, output_dir, video.stem, min_clip_duration_sec=min_clip_duration)
                    results.append((video.name, "ok", f"{len(clips)} clip(s)"))

        except Exception as exc:
            console.print(f"[red]Failed: {exc}[/red]")
            results.append((video.name, "error", str(exc)))

    summary = Table(title="Batch summary")
    summary.add_column("Video")
    summary.add_column("Status")
    summary.add_column("Detail")
    status_colors = {"ok": "green", "error": "red", "skipped": "yellow", "dry-run": "yellow"}
    for name, status, detail in results:
        color = status_colors.get(status, "white")
        summary.add_row(name, f"[{color}]{status}[/{color}]", detail)
    console.print(summary)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
