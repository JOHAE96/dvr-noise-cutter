"""Per-frame noise detectors and temporal segmentation.

Every ``score_*`` function returns a float, nominally in ``[0.0, 1.0]``,
where higher means more noise-like. This shared convention lets the scores
be linearly combined in :func:`combine_scores` without per-detector sign
flips.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import scipy.fft

Frame = np.ndarray
"""HxWx3 BGR uint8 frame, as produced by cv2.VideoCapture.read()."""


def score_saturation(frame: Frame) -> float:
    """Mean HSV saturation, inverted and normalized. Low saturation -> high score."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mean_saturation = float(hsv[:, :, 1].mean()) / 255.0
    return float(np.clip(1.0 - mean_saturation, 0.0, 1.0))


def score_frame_diff(prev_gray: np.ndarray, curr_gray: np.ndarray) -> float:
    """Mean absolute pixel difference between two grayscale frames, normalized by 255."""
    diff = cv2.absdiff(prev_gray, curr_gray)
    return float(np.clip(float(diff.mean()) / 255.0, 0.0, 1.0))


def score_fft_high_freq(frame: Frame, cutoff_fraction: float = 0.15) -> float:
    """Ratio of high-frequency spectral energy to total energy.

    ``cutoff_fraction`` sets the radius (as a fraction of the maximum radius
    in the shifted spectrum) beyond which energy counts as "high frequency".
    Real footage concentrates energy near the low-frequency center; flat/noisy
    signal spreads more energy into the outer band.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float64)
    spectrum = scipy.fft.fftshift(scipy.fft.fft2(gray))
    magnitude_sq = np.abs(spectrum) ** 2

    h, w = magnitude_sq.shape
    cy, cx = h / 2.0, w / 2.0
    y, x = np.ogrid[:h, :w]
    radius = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
    max_radius = np.hypot(cy, cx)
    cutoff = cutoff_fraction * max_radius

    total_energy = magnitude_sq.sum()
    if total_energy <= 0:
        return 0.0
    high_energy = magnitude_sq[radius > cutoff].sum()
    return float(np.clip(high_energy / total_energy, 0.0, 1.0))


def score_edge_incoherence(
    frame: Frame, canny_threshold1: float = 100.0, canny_threshold2: float = 200.0
) -> float:
    """1 minus normalized mean contour length. Many short, fragmented edges -> high score."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, canny_threshold1, canny_threshold2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0

    arc_lengths = [cv2.arcLength(c, closed=False) for c in contours]
    mean_arc_length = float(np.mean(arc_lengths))
    diagonal = float(np.hypot(*gray.shape))
    normalized_length = min(mean_arc_length / diagonal, 1.0)
    return float(np.clip(1.0 - normalized_length, 0.0, 1.0))


@dataclass(frozen=True)
class DetectorWeights:
    """Combination weights for the four detectors. Retune here, not at call sites."""

    saturation: float = 0.30
    frame_diff: float = 0.20
    fft_high_freq: float = 0.30
    edge_incoherence: float = 0.20


def combine_scores(
    saturation: float,
    frame_diff: float,
    fft_high_freq: float,
    edge_incoherence: float,
    weights: DetectorWeights = DetectorWeights(),
) -> float:
    """Weighted average of the four detector scores."""
    total_weight = (
        weights.saturation
        + weights.frame_diff
        + weights.fft_high_freq
        + weights.edge_incoherence
    )
    weighted_sum = (
        weights.saturation * saturation
        + weights.frame_diff * frame_diff
        + weights.fft_high_freq * fft_high_freq
        + weights.edge_incoherence * edge_incoherence
    )
    return weighted_sum / total_weight


@dataclass
class FrameScore:
    sample_index: int
    """Index into the sampled frame sequence, not the raw video frame number."""
    timestamp_sec: float
    saturation: float
    frame_diff: float
    fft_high_freq: float
    edge_incoherence: float
    combined: float
    is_noise: bool


@dataclass(frozen=True)
class NoiseSegment:
    start_sec: float
    end_sec: float

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


def get_video_fps(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            raise ValueError(f"Could not determine FPS for video file: {video_path}")
        return float(fps)
    finally:
        cap.release()


def analyze_video_frames(
    video_path: Path,
    sample_rate: int = 5,
    weights: DetectorWeights = DetectorWeights(),
    threshold: float = 0.5,
    on_frame_read: Callable[[int], None] | None = None,
) -> list[FrameScore]:
    """Sample every ``sample_rate``-th frame and compute per-frame detector scores.

    ``on_frame_read`` is called with the raw frame index after each frame is
    read (sampled or not), so callers can drive a progress indicator.
    """
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            raise ValueError(f"Could not determine FPS for video file: {video_path}")

        scores: list[FrameScore] = []
        prev_gray: np.ndarray | None = None
        raw_index = 0
        sample_index = 0

        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if raw_index % sample_rate == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                saturation = score_saturation(frame)
                frame_diff = score_frame_diff(prev_gray, gray) if prev_gray is not None else 0.0
                fft_high_freq = score_fft_high_freq(frame)
                edge_incoherence = score_edge_incoherence(frame)
                combined = combine_scores(saturation, frame_diff, fft_high_freq, edge_incoherence, weights)

                scores.append(
                    FrameScore(
                        sample_index=sample_index,
                        timestamp_sec=raw_index / fps,
                        saturation=saturation,
                        frame_diff=frame_diff,
                        fft_high_freq=fft_high_freq,
                        edge_incoherence=edge_incoherence,
                        combined=combined,
                        is_noise=combined >= threshold,
                    )
                )
                prev_gray = gray
                sample_index += 1

            if on_frame_read is not None:
                on_frame_read(raw_index)
            raw_index += 1

        return scores
    finally:
        cap.release()


def segments_from_scores(
    scores: list[FrameScore],
    min_segment_duration_sec: float,
    frame_interval_sec: float,
) -> list[NoiseSegment]:
    """Run-length encode ``is_noise`` over time, filter by duration, emit segments.

    ``frame_interval_sec`` (``sample_rate / fps``) is required to extrapolate
    the end timestamp of a run that reaches the last sampled frame, so a
    noise segment that lasts until the end of the video isn't reported as
    ending one sample-stride too early.
    """
    if not scores:
        return []

    runs: list[tuple[bool, int, int]] = []
    current_value = scores[0].is_noise
    run_start = 0
    for i in range(1, len(scores)):
        if scores[i].is_noise != current_value:
            runs.append((current_value, run_start, i - 1))
            current_value = scores[i].is_noise
            run_start = i
    runs.append((current_value, run_start, len(scores) - 1))

    segments: list[NoiseSegment] = []
    for value, start_idx, end_idx in runs:
        if not value:
            continue
        start_sec = scores[start_idx].timestamp_sec
        if end_idx + 1 < len(scores):
            end_sec = scores[end_idx + 1].timestamp_sec
        else:
            end_sec = scores[end_idx].timestamp_sec + frame_interval_sec

        segment = NoiseSegment(start_sec=start_sec, end_sec=end_sec)
        if segment.duration_sec >= min_segment_duration_sec:
            segments.append(segment)

    return segments
