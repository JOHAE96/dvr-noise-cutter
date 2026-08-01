from unittest.mock import patch

import pytest

from dvr_noise_cutter.cutter import ffprobe_duration, invert_segments
from dvr_noise_cutter.detector import NoiseSegment


def test_invert_segments_no_noise():
    keep = invert_segments([], total_duration_sec=100.0)
    assert keep == [NoiseSegment(0.0, 100.0)]


def test_invert_segments_noise_at_start():
    keep = invert_segments([NoiseSegment(0.0, 10.0)], total_duration_sec=100.0)
    assert len(keep) == 1
    assert keep[0].start_sec == pytest.approx(10.0)
    assert keep[0].end_sec == pytest.approx(100.0)


def test_invert_segments_noise_at_end():
    keep = invert_segments([NoiseSegment(90.0, 100.0)], total_duration_sec=100.0)
    assert len(keep) == 1
    assert keep[0].start_sec == pytest.approx(0.0)
    assert keep[0].end_sec == pytest.approx(90.0)


def test_invert_segments_noise_in_middle():
    keep = invert_segments([NoiseSegment(40.0, 60.0)], total_duration_sec=100.0)
    assert len(keep) == 2
    assert keep[0].start_sec == pytest.approx(0.0)
    assert keep[0].end_sec == pytest.approx(40.0)
    assert keep[1].start_sec == pytest.approx(60.0)
    assert keep[1].end_sec == pytest.approx(100.0)


def test_invert_segments_all_noise():
    keep = invert_segments([NoiseSegment(0.0, 100.0)], total_duration_sec=100.0)
    assert keep == []


def test_invert_segments_adjacent_noise_segments():
    keep = invert_segments(
        [NoiseSegment(10.0, 20.0), NoiseSegment(20.0, 30.0)],
        total_duration_sec=100.0,
    )
    assert len(keep) == 2
    assert keep[0].end_sec == pytest.approx(10.0)
    assert keep[1].start_sec == pytest.approx(30.0)


def test_ffprobe_duration_parses_output():
    with patch("dvr_noise_cutter.cutter.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "12.345\n"
        mock_run.return_value.stderr = ""
        assert ffprobe_duration("dummy.mp4") == pytest.approx(12.345)
