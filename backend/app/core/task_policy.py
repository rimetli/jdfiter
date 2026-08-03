from datetime import timedelta


def retry_delay_seconds(
    attempt_count: int, base_seconds: int, max_seconds: int
) -> int:
    """Return bounded exponential backoff for an attempt that has just failed."""
    exponent = max(attempt_count - 1, 0)
    return min(base_seconds * (2**exponent), max_seconds)


def retry_available_after(attempt_count: int, base_seconds: int, max_seconds: int) -> timedelta:
    return timedelta(seconds=retry_delay_seconds(attempt_count, base_seconds, max_seconds))
