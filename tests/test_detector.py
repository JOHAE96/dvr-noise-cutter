import cv2
import numpy as np
import pytest

from dvr_noise_cutter.detector import (
    DetectorWeights,
    FrameScore,
    combine_scores,
    score_edge_incoherence,
    score_fft_high_freq,
    score_frame_diff,
    score_saturation,
    segments_from_scores,
)


def _solid_frame(h: int, w: int, bgr: tuple[int, int, int]) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = bgr
    return frame


def _random_frame(h: int, w: int) -> np.ndarray:
    return np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)


def _gradient_frame(h: int, w: int) -> np.ndarray:
    row = np.linspace(0, 255, w).astype(np.uint8)
    tiled = np.tile(row, (h, 1))
    return np.stack([tiled, tiled, tiled], axis=-1).astype(np.uint8)


def _shapes_frame(h: int, w: int) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.rectangle(frame, (10, 10), (w - 10, h - 10), (255, 255, 255), 2)
    cv2.circle(frame, (w // 2, h // 2), min(h, w) // 4, (255, 255, 255), 2)
    cv2.line(frame, (0, 0), (w - 1, h - 1), (255, 255, 255), 2)
    return frame


def _make_scores(flags: list[bool], frame_interval_sec: float) -> list[FrameScore]:
    return [
        FrameScore(
            sample_index=i,
            timestamp_sec=i * frame_interval_sec,
            saturation=0.0,
            frame_diff=0.0,
            fft_high_freq=0.0,
            edge_incoherence=0.0,
            combined=1.0 if flag else 0.0,
            is_noise=flag,
        )
        for i, flag in enumerate(flags)
    ]


# -- score_saturation ---------------------------------------------------


def test_score_saturation_gray_higher_than_color():
    gray = _solid_frame(64, 64, (128, 128, 128))
    color = _solid_frame(64, 64, (255, 0, 0))
    assert score_saturation(gray) > score_saturation(color)


def test_score_saturation_range():
    gray = _solid_frame(64, 64, (128, 128, 128))
    color = _solid_frame(64, 64, (255, 0, 0))
    assert 0.0 <= score_saturation(gray) <= 1.0
    assert 0.0 <= score_saturation(color) <= 1.0


# -- score_frame_diff -----------------------------------------------------


def test_score_frame_diff_identical_pair_is_zero():
    np.random.seed(0)
    gray = cv2.cvtColor(_random_frame(64, 64), cv2.COLOR_BGR2GRAY)
    assert score_frame_diff(gray, gray) == pytest.approx(0.0)


def test_score_frame_diff_random_pair_higher_than_identical():
    np.random.seed(0)
    gray1 = cv2.cvtColor(_random_frame(64, 64), cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(_random_frame(64, 64), cv2.COLOR_BGR2GRAY)
    assert score_frame_diff(gray1, gray2) > score_frame_diff(gray1, gray1)


# -- score_fft_high_freq ---------------------------------------------------


def test_score_fft_high_freq_noise_higher_than_smooth():
    np.random.seed(0)
    noise = _random_frame(128, 128)
    smooth = _gradient_frame(128, 128)
    assert score_fft_high_freq(noise) > score_fft_high_freq(smooth)


# -- score_edge_incoherence -------------------------------------------------


def test_score_edge_incoherence_noise_higher_than_shapes():
    np.random.seed(0)
    noise = _random_frame(128, 128)
    shapes = _shapes_frame(128, 128)
    assert score_edge_incoherence(noise) > score_edge_incoherence(shapes)


def test_score_edge_incoherence_uniform_frame_no_crash():
    uniform = _solid_frame(64, 64, (128, 128, 128))
    score = score_edge_incoherence(uniform)
    assert 0.0 <= score <= 1.0


# -- combine_scores ----------------------------------------------------------


def test_combine_scores_weighted_average():
    weights = DetectorWeights(saturation=1.0, frame_diff=1.0, fft_high_freq=1.0, edge_incoherence=1.0)
    result = combine_scores(0.2, 0.4, 0.6, 0.8, weights)
    assert result == pytest.approx((0.2 + 0.4 + 0.6 + 0.8) / 4)


def test_combine_scores_default_weights_extremes_in_range():
    assert combine_scores(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)
    assert combine_scores(1.0, 1.0, 1.0, 1.0) == pytest.approx(1.0)


# -- segments_from_scores -----------------------------------------------------


def test_segments_from_scores_empty_input():
    assert segments_from_scores([], min_segment_duration_sec=1.0, frame_interval_sec=0.2) == []


def test_segments_from_scores_single_short_run_dropped():
    flags = [False, False, True, False, False]
    scores = _make_scores(flags, frame_interval_sec=0.2)
    segments = segments_from_scores(scores, min_segment_duration_sec=1.0, frame_interval_sec=0.2)
    assert segments == []


def test_segments_from_scores_long_run_kept_with_correct_bounds():
    flags = [False, False, True, True, True, True, True, False, False]
    frame_interval_sec = 0.2
    scores = _make_scores(flags, frame_interval_sec)
    segments = segments_from_scores(scores, min_segment_duration_sec=0.5, frame_interval_sec=frame_interval_sec)
    assert len(segments) == 1
    assert segments[0].start_sec == pytest.approx(2 * frame_interval_sec)
    assert segments[0].end_sec == pytest.approx(7 * frame_interval_sec)


def test_segments_from_scores_starts_at_first_frame():
    flags = [True, True, True, False, False]
    frame_interval_sec = 0.2
    scores = _make_scores(flags, frame_interval_sec)
    segments = segments_from_scores(scores, min_segment_duration_sec=0.3, frame_interval_sec=frame_interval_sec)
    assert len(segments) == 1
    assert segments[0].start_sec == pytest.approx(scores[0].timestamp_sec)


def test_segments_from_scores_ends_mid_video():
    flags = [False, False, True, True, True]
    frame_interval_sec = 0.2
    scores = _make_scores(flags, frame_interval_sec)
    segments = segments_from_scores(scores, min_segment_duration_sec=0.3, frame_interval_sec=frame_interval_sec)
    assert len(segments) == 1
    assert segments[0].end_sec == pytest.approx(scores[-1].timestamp_sec + frame_interval_sec)


def test_segments_from_scores_all_noise():
    flags = [True] * 5
    frame_interval_sec = 0.2
    scores = _make_scores(flags, frame_interval_sec)
    segments = segments_from_scores(scores, min_segment_duration_sec=0.3, frame_interval_sec=frame_interval_sec)
    assert len(segments) == 1
    assert segments[0].start_sec == pytest.approx(0.0)
    assert segments[0].end_sec == pytest.approx(5 * frame_interval_sec)


def test_segments_from_scores_multiple_runs_in_order():
    flags = [True, True, True, False, False, False, True, True, True]
    frame_interval_sec = 0.2
    scores = _make_scores(flags, frame_interval_sec)
    segments = segments_from_scores(scores, min_segment_duration_sec=0.3, frame_interval_sec=frame_interval_sec)
    assert len(segments) == 2
    assert segments[0].start_sec == pytest.approx(0.0)
    assert segments[0].end_sec == pytest.approx(3 * frame_interval_sec)
    assert segments[1].start_sec == pytest.approx(6 * frame_interval_sec)
    assert segments[1].end_sec == pytest.approx(9 * frame_interval_sec)
