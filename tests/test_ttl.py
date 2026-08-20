from pathlib import Path

from dvr_noise_cutter.web.ttl import find_expired_job_dirs


def test_find_expired_job_dirs_mixed_ages():
    now = 1_000_000.0
    dirs = [
        (Path("/a"), now - 3600),      # 1h old — not expired
        (Path("/b"), now - 100_000),   # ~27.8h old — expired
        (Path("/c"), now),             # brand new — not expired
    ]
    assert find_expired_job_dirs(dirs, now, ttl_hours=24) == [Path("/b")]


def test_find_expired_job_dirs_empty_input():
    assert find_expired_job_dirs([], now=1_000_000.0, ttl_hours=24) == []


def test_find_expired_job_dirs_all_expired():
    now = 1_000_000.0
    dirs = [(Path("/a"), 0.0), (Path("/b"), 100.0)]
    assert find_expired_job_dirs(dirs, now, ttl_hours=1) == [Path("/a"), Path("/b")]
