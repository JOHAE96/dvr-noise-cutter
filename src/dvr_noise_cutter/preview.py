"""Debug plot of the noise score curve over time (--preview).

Kept separate from detector.py/cutter.py so matplotlib stays out of the
import path for the core detection/cutting logic and its unit tests.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from dvr_noise_cutter.detector import FrameScore, NoiseSegment


def save_preview_plot(
    scores: list[FrameScore],
    segments: list[NoiseSegment],
    threshold: float,
    out_path: Path,
) -> None:
    timestamps = [s.timestamp_sec for s in scores]
    combined = [s.combined for s in scores]

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(timestamps, combined, linewidth=1, label="combined noise score")
    ax.axhline(threshold, color="red", linestyle="--", label=f"threshold ({threshold:.2f})")
    for segment in segments:
        ax.axvspan(segment.start_sec, segment.end_sec, color="red", alpha=0.2)

    ax.set_xlabel("time (s)")
    ax.set_ylabel("noise score")
    ax.set_ylim(0.0, 1.0)
    ax.set_title("Noise score over time")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
