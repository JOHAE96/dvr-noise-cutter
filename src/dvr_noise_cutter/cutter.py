"""ffprobe/ffmpeg orchestration: inverting noise segments into keep intervals,
extracting them (stream copy with re-encode fallback), and concatenating.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dvr_noise_cutter.detector import NoiseSegment


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"ffprobe failed to read duration for {path}: {result.stderr.strip()}")
    return float(result.stdout.strip())


def has_audio_stream(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def invert_segments(
    noise_segments: list[NoiseSegment],
    total_duration_sec: float,
    min_keep_duration_sec: float = 0.05,
) -> list[NoiseSegment]:
    """Complement of (sorted, possibly overlapping/adjacent) noise segments
    against [0, total_duration_sec]. Drops keep intervals shorter than
    ``min_keep_duration_sec`` to avoid degenerate ffmpeg clips.
    """
    if not noise_segments:
        return [NoiseSegment(0.0, total_duration_sec)]

    keep: list[NoiseSegment] = []
    cursor = 0.0
    for seg in sorted(noise_segments, key=lambda s: s.start_sec):
        start = max(seg.start_sec, 0.0)
        if start - cursor >= min_keep_duration_sec:
            keep.append(NoiseSegment(cursor, start))
        cursor = max(cursor, seg.end_sec)

    if total_duration_sec - cursor >= min_keep_duration_sec:
        keep.append(NoiseSegment(cursor, total_duration_sec))

    return keep


@dataclass
class ExtractResult:
    path: Path
    used_copy: bool
    expected_duration: float
    actual_duration: float


def _safe_duration(path: Path) -> float | None:
    try:
        return ffprobe_duration(path)
    except RuntimeError:
        return None


def extract_segment(
    src: Path,
    start_sec: float,
    end_sec: float,
    out_path: Path,
    has_audio: bool,
    duration_tolerance_sec: float = 0.5,
) -> ExtractResult:
    """Extract [start_sec, end_sec) from src into out_path.

    Tries a fast stream-copy first (keyframe-snapped, not frame-accurate);
    validates the resulting duration and falls back to a frame-accurate
    re-encode if the copy failed or drifted beyond tolerance.
    """
    duration = end_sec - start_sec

    copy_result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start_sec), "-i", str(src), "-t", str(duration),
            "-c", "copy", "-avoid_negative_ts", "make_zero",
            str(out_path),
        ],
        capture_output=True, text=True,
    )
    if copy_result.returncode == 0 and out_path.exists():
        actual = _safe_duration(out_path)
        if actual is not None and abs(actual - duration) <= duration_tolerance_sec:
            return ExtractResult(path=out_path, used_copy=True, expected_duration=duration, actual_duration=actual)

    audio_flags = ["-c:a", "aac", "-b:a", "128k"] if has_audio else ["-an"]
    reencode_result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start_sec), "-i", str(src), "-t", str(duration),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            *audio_flags,
            str(out_path),
        ],
        capture_output=True, text=True,
    )
    if reencode_result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to extract segment [{start_sec}, {end_sec}]: {reencode_result.stderr.strip()}"
        )

    actual = ffprobe_duration(out_path)
    return ExtractResult(path=out_path, used_copy=False, expected_duration=duration, actual_duration=actual)


def concat_segments(segment_paths: list[Path], out_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        list_file = Path(tmp_dir) / "concat_list.txt"
        list_file.write_text("".join(f"file '{p.resolve()}'\n" for p in segment_paths))

        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed to concatenate segments: {result.stderr.strip()}")


def cut_noise_segments(
    src: Path,
    noise_segments: list[NoiseSegment],
    out_path: Path,
    duration_tolerance_sec: float = 0.5,
) -> None:
    """Detects the keep intervals (complement of noise_segments), extracts
    and concatenates them into out_path.
    """
    total_duration = ffprobe_duration(src)
    keep_segments = invert_segments(noise_segments, total_duration)
    if not keep_segments:
        raise ValueError("Entire video was detected as noise; nothing to keep.")

    has_audio = has_audio_stream(src)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        segment_paths: list[Path] = []
        for i, seg in enumerate(keep_segments):
            seg_path = tmp_path / f"segment_{i:04d}.mp4"
            extract_segment(src, seg.start_sec, seg.end_sec, seg_path, has_audio, duration_tolerance_sec)
            segment_paths.append(seg_path)

        if len(segment_paths) == 1:
            shutil.copy(segment_paths[0], out_path)
        else:
            concat_segments(segment_paths, out_path)
