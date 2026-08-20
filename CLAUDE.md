# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                 # install/update dependencies
uv run pytest           # run the full test suite
uv run pytest tests/test_detector.py::test_score_saturation_gray_higher_than_color  # single test
uv run dvr-noise-cutter analyze <video.mp4>   # detect noise segments, print table
uv run dvr-noise-cutter cut <video.mp4> --output clean.mp4   # remove noise segments, one output file
uv run dvr-noise-cutter split <video.mp4> --output-dir clips/   # one clip per interval between noise segments
uv run dvr-noise-cutter batch cut *.mp4 --output-dir cleaned/   # run analyze/cut/split over many videos or a directory
```

There is no separate lint/build step; this is a plain uv-managed package (`uv_build` backend).

## Architecture

Pipeline: `detector.py` scores frames → `cli.py` orchestrates → `cutter.py` cuts the source video with ffmpeg. `preview.py` is a leaf consumer of `detector.py`'s data types for the `--preview` debug plot.

- **`detector.py`** — all frame-analysis logic, no ffmpeg/subprocess dependency.
  - Four independent `score_*(frame) -> float` functions (saturation, frame-diff, FFT high-frequency ratio, edge incoherence), each returning `[0, 1]` where **higher always means more noise-like** — this shared convention is what allows `combine_scores` to linearly combine them without sign flips. Any new detector must follow the same convention.
  - `DetectorWeights` is the single place combination weights live; never hardcode weight values elsewhere.
  - `analyze_video_frames` owns the only `cv2.VideoCapture` frame-reading loop and the only stateful piece of detection (the previous *sampled* frame's grayscale buffer, needed for `score_frame_diff`). All four `score_*` functions stay pure/stateless so they're testable with synthetic numpy frames.
  - `segments_from_scores` run-length-encodes `FrameScore.is_noise` over time, then filters by `min_segment_duration_sec`. It requires `frame_interval_sec` (`sample_rate / fps`) as an explicit argument to correctly extrapolate the end timestamp of a run that reaches the last sampled frame — don't let this be silently defaulted/guessed by a caller.

- **`cutter.py`** — all ffmpeg/ffprobe orchestration, via plain `subprocess.run`, not `ffmpeg-python`.
  - `invert_segments` complements noise segments against total duration to get "keep" intervals (this, not the noise segments themselves, is what gets extracted). Its `min_keep_duration_sec` param serves two different callers with two different meanings: `cut_noise_segments` uses the tiny default (`0.05`s, just avoiding degenerate zero-length clips), `split_at_noise_segments` passes `min_clip_duration_sec` (default `3.0`s) through it to actually filter out too-short clips between dropouts.
  - `extract_segment` always tries `-c copy` first (fast, keyframe-snapped) and validates the result's duration via `ffprobe_duration` against `duration_tolerance_sec`; only falls back to a `libx264`/`aac` re-encode (frame-accurate) if the copy attempt fails or drifts. Keep this copy-then-validate-then-fallback order when touching extraction logic — it's the reason cuts are fast in the common case without sacrificing correctness.
  - `cut_noise_segments` and `split_at_noise_segments` both build on `invert_segments` + `extract_segment` and differ only in what happens to the keep intervals afterward: `cut_noise_segments` concatenates them into one output via ffmpeg's concat demuxer (requires all intermediate segments to share codec parameters, guaranteed by construction — either literal stream copies of the source, or re-encoded with identical fixed settings); `split_at_noise_segments` writes each keep interval as its own numbered output file (`{stem}_part{i:03d}.mp4`) and skips concatenation entirely.

- **`cli.py`** — Typer app wiring `analyze`/`cut`/`split`/`batch` to the above.
  - `_run_detection` is the shared helper all single-video commands call (avoid duplicating the `analyze_video_frames` + `segments_from_scores` pair). Progress reporting is driven by `analyze_video_frames`'s `on_frame_read` callback, not a separate pass over the video.
  - `batch` is a dedicated command (not multi-file arguments on `analyze`/`cut`/`split`, which stay single-video) that dispatches per-video to the same underlying functions (`_run_detection`, `cut_noise_segments`, `split_at_noise_segments`) inside a per-video `try/except`. Catching broad `Exception` there is intentional, not sloppy: batch input is typically an entire SD-card dump where some files may be corrupt/unreadable, and resilience across that is the entire point of the command — one bad file must not abort the run. Directories passed as `videos` are expanded via `_expand_video_paths` (non-recursive `.mp4`/`.mov`/`.avi` scan).

### Real vs. synthetic noise

Real analog static/snow is essentially **grayscale** per-pixel noise (R≈G≈B), which is why `score_saturation` is a meaningful detector. Synthetic test frames must reflect this — independent per-channel random RGB noise (`np.random.randint(0, 256, (h, w, 3))`) looks nothing like real DVR static from the saturation detector's point of view (it reads as highly saturated, not desaturated) and will not be flagged as noise by the combined score. When generating synthetic noise frames for manual testing, build a single-channel random array and convert with `cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)`.

### Data flow types

`FrameScore` and `NoiseSegment` (in `detector.py`) are dataclasses, not tuples, and flow unchanged through JSON export (`dataclasses.asdict`), `cutter.py`, and `preview.py`. `NoiseSegment.duration_sec` is a derived `@property`, not a stored field — it won't appear in `asdict()` output.
