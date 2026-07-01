"""Unit tests for AIQE shared utilities."""
import pytest
from aiqe.shared.utils import (
    Timer,
    format_duration,
    hash_content,
    retry_with_backoff,
    slugify,
    truncate,
    deep_merge,
)


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_characters(self):
        assert slugify("User Authentication!") == "user-authentication"

    def test_multiple_spaces(self):
        assert slugify("My  Feature   Name") == "my-feature-name"


class TestTruncate:
    def test_no_truncation_needed(self):
        assert truncate("short", max_length=100) == "short"

    def test_truncates_correctly(self):
        result = truncate("hello world", max_length=8)
        assert len(result) == 8
        assert result.endswith("...")

    def test_exact_length(self):
        assert truncate("hello", max_length=5) == "hello"


class TestHashContent:
    def test_same_content_same_hash(self):
        assert hash_content("test") == hash_content("test")

    def test_different_content_different_hash(self):
        assert hash_content("test1") != hash_content("test2")

    def test_returns_string(self):
        assert isinstance(hash_content("test"), str)


class TestFormatDuration:
    def test_milliseconds(self):
        assert format_duration(0.5) == "500ms"

    def test_seconds(self):
        assert "s" in format_duration(1.5)

    def test_minutes(self):
        assert "m" in format_duration(90.0)

    def test_hours(self):
        assert "h" in format_duration(3661.0)


class TestDeepMerge:
    def test_simple_merge(self):
        result = deep_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_override_takes_precedence(self):
        result = deep_merge({"a": 1}, {"a": 2})
        assert result["a"] == 2

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 99, "z": 3}}
        result = deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 99, "z": 3}}

    def test_does_not_modify_originals(self):
        base = {"a": 1}
        override = {"b": 2}
        deep_merge(base, override)
        assert base == {"a": 1}


class TestTimer:
    def test_measures_elapsed_time(self):
        import time
        with Timer() as t:
            time.sleep(0.01)
        assert t.elapsed_seconds >= 0.01

    def test_elapsed_ms(self):
        import time
        with Timer() as t:
            time.sleep(0.01)
        assert t.elapsed_ms >= 10


class TestRetryWithBackoff:
    def test_returns_correct_count(self):
        delays = retry_with_backoff(max_attempts=3)
        assert len(delays) == 3

    def test_delays_are_non_negative(self):
        delays = retry_with_backoff(max_attempts=5)
        assert all(d >= 0 for d in delays)

    def test_respects_max_delay(self):
        delays = retry_with_backoff(max_attempts=10, max_delay=5.0)
        assert all(d <= 5.5 for d in delays)
