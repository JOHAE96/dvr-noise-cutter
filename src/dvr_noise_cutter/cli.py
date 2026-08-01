"""Typer CLI: analyze and cut commands for finding/removing DVR noise segments."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import cv2
import typer
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from dvr_noise_cutter.cutter import cut_noise_segments
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
