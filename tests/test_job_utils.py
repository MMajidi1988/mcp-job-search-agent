"""Tests for shared job utilities."""

from datetime import UTC, datetime, timedelta

from mcp_job_search.job_utils import deadline_is_still_open, extract_jwt_from_text


def test_extract_jwt_from_text_prefix() -> None:
    body = "Current public token for Nav Job Vacancy Feed:\neyJhbGciOiJIUzI1NiJ9.x.y"
    assert extract_jwt_from_text(body) == "eyJhbGciOiJIUzI1NiJ9.x.y"


def test_deadline_open_future() -> None:
    future = (datetime.now(UTC) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert deadline_is_still_open(future)


def test_deadline_closed_past() -> None:
    past = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert not deadline_is_still_open(past)
