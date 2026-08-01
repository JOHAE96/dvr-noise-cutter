# FPV DVR Noise Cutter

A CLI tool that analyzes FPV analog-DVR recordings (mp4/mov) and automatically detects
segments of pure signal noise ("static/snow" from video-feed dropout, no drone camera
picture) — to list them as timestamps, cut them out, or split the recording into
separate clips at the dropout boundaries (e.g. one clip per battery pack).

## How it works

For a sample of frames (every Nth frame, configurable), four independent detectors each
produce a score in `[0, 1]` where higher means "more noise-like":

- **Saturation** — mean HSV saturation, inverted (static tends to be desaturated/grayish).
- **Frame diff** — mean absolute difference between consecutive sampled frames.
- **FFT** — ratio of high-frequency to total spectral energy (noise has a flatter spectrum).
- **Edge coherence** — Canny edges vs. contour length (noise produces many short,
  disconnected edge fragments instead of long coherent contours).

The four scores are combined into a weighted average, thresholded, and then temporally
smoothed (run-length encoded over time, dropping runs shorter than a minimum segment
duration) to produce contiguous noise segments.

## Installation

Requires [uv](https://docs.astral.sh/uv/) and `ffmpeg`/`ffprobe` on your `PATH`.

```bash
uv sync
```

## Usage

### Analyze a video

```bash
uv run dvr-noise-cutter analyze video.mp4
```

Prints detected noise segments as a table. Useful options:

```bash
uv run dvr-noise-cutter analyze video.mp4 \
  --threshold 0.5 \
  --min-segment-duration 1.0 \
  --sample-rate 5 \
  --json segments.json \
  --preview
```

- `--json <path>` — also export the detected segments as JSON.
- `--preview` — save a debug plot (`<video>.preview.png`) of the noise score curve over
  time, with the threshold line and detected segments shaded.

### Cut noise segments out of a video

```bash
uv run dvr-noise-cutter cut video.mp4 --output clean.mp4
```

Detects noise segments, then extracts and concatenates the remaining ("keep") intervals.
Segments are extracted with `ffmpeg -c copy` where possible (fast, no re-encode) and
fall back to a re-encode (`libx264`/`aac`) per-segment when a stream-copy cut isn't
frame-accurate enough.

```bash
uv run dvr-noise-cutter cut video.mp4 --output clean.mp4 --dry-run
```

`--dry-run` only detects and prints segments — no output file is written.

### Split a video into separate clips (e.g. one per battery pack)

```bash
uv run dvr-noise-cutter split video.mp4 --output-dir clips/
```

Instead of removing noise and concatenating the rest into one file, `split` extracts
each interval *between* noise segments as its own clip: `video_part001.mp4`,
`video_part002.mp4`, etc. Useful when one DVR recording spans several flights, separated
by a dropout when the video link is reconnected between battery packs.

```bash
uv run dvr-noise-cutter split video.mp4 --output-dir clips/ --min-clip-duration 3.0 --dry-run
```

`--min-clip-duration` (default `3.0`s) drops resulting clips shorter than this — distinct
from `--min-segment-duration`, which filters *noise* runs, not the clips between them.
`--dry-run` prints the would-be clip boundaries without writing files.

### Batch processing

```bash
uv run dvr-noise-cutter batch cut *.mp4 --output-dir cleaned/
uv run dvr-noise-cutter batch split /path/to/sd-card-dump/ --output-dir clips/
uv run dvr-noise-cutter batch analyze *.mp4 --output-dir results/ --json
```

Runs `analyze`, `cut`, or `split` over multiple videos in one invocation. Accepts
individual video files and/or directories (directories are scanned non-recursively for
`.mp4`/`.mov` files). A failure on one file (corrupt/unreadable video, ffmpeg error)
doesn't abort the run — it's reported as `error` in the summary table while the rest of
the batch continues.

### Options (shared by `analyze`, `cut`, `split`, `batch`)

| Option | Default | Description |
|---|---|---|
| `--threshold` | `0.5` | Combined noise-score threshold in `[0, 1]`. |
| `--min-segment-duration` | `1.0` | Minimum duration (seconds) for a detected noise segment; shorter outliers are ignored. |
| `--sample-rate` | `5` | Analyze every Nth frame. |
| `--preview` | off | Save a debug plot of the score curve. |
| `--min-clip-duration` | `3.0` | (`split`/`batch split`) Minimum duration for a resulting clip. |

## Development

```bash
uv run pytest
```

Detector weights live in `DetectorWeights` (`src/dvr_noise_cutter/detector.py`) and can be
retuned in one place without touching call sites.

## Project layout

```
src/dvr_noise_cutter/
├── detector.py   # per-frame score functions, combination, temporal segmentation
├── cutter.py     # ffprobe/ffmpeg extraction, concatenation, and per-clip splitting
├── preview.py    # debug score-curve plot
└── cli.py        # Typer CLI (analyze, cut, split, batch)
tests/
├── test_detector.py
└── test_cutter.py
```
