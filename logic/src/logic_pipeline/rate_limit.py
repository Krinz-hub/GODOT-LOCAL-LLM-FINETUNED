"""Rate limiting and backoff utilities for external data sources."""

import time
import threading
from typing import Optional
from logic_pipeline.logging_config import get_logger

logger = get_logger("rate_limit")


class RateLimiter:
    """Thread-safe token bucket rate limiter."""

    def __init__(self, requests_per_minute: int = 30):
        self.capacity = max(1, requests_per_minute)
        self.rate = self.capacity / 60.0  # Tokens per second
        self.tokens = float(self.capacity)
        self.last_check = time.time()
        self._lock = threading.Lock()

    def acquire(self, tokens: int = 1, timeout: Optional[float] = 60.0) -> bool:
        """Blocks until sufficient tokens are available or timeout expires."""
        start_time = time.time()
        while True:
            with self._lock:
                now = time.time()
                elapsed = now - self.last_check
                self.last_check = now
                self.tokens = min(float(self.capacity), self.tokens + elapsed * self.rate)

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

            if timeout is not None and (time.time() - start_time) > timeout:
                logger.warning("RateLimiter acquire timed out after %s seconds", timeout)
                return False

            # Wait briefly before re-checking
            time.sleep(0.05)


def backoff_retry(
    func,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    initial_delay: float = 1.0,
    allowed_exceptions: tuple = (Exception,),
):
    """Executes a function with exponential backoff retry."""
    delay = initial_delay
    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except allowed_exceptions as exc:
            last_exception = exc
            if attempt == max_retries:
                logger.error("Function failed after %s retries: %s", max_retries, exc)
                raise
            logger.warning(
                "Attempt %s failed with %s. Retrying in %.2f seconds...",
                attempt,
                exc,
                delay,
            )
            time.sleep(delay)
            delay *= backoff_factor

    if last_exception:
        raise last_exception
