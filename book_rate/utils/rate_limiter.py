import logging
import random
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DomainRateLimiter:
    """Thread-safe rate limiter providing minimum time intervals (cooldown) between requests.
    Supports per-source/domain cooldowns and random jitter to avoid WAF pattern detection.
    """

    def __init__(self, default_cooldown: float = 1.0, jitter_range: tuple = (0.1, 0.3)):
        self.default_cooldown = default_cooldown
        self.jitter_range = jitter_range
        self._last_request_times: Dict[str, float] = {}
        self._custom_cooldowns: Dict[str, float] = {}
        self._lock = threading.Lock()

    def set_cooldown(self, key: str, cooldown: float) -> None:
        """Set a custom cooldown interval in seconds for a specific source/domain."""
        with self._lock:
            self._custom_cooldowns[key] = cooldown

    def get_cooldown(self, key: str) -> float:
        """Get the configured cooldown interval for a specific source/domain."""
        with self._lock:
            return self._custom_cooldowns.get(key, self.default_cooldown)

    def wait_if_needed(self, key: str, custom_cooldown: Optional[float] = None) -> float:
        """Ensure the elapsed time since the last request for the given key satisfies the cooldown.
        Blocks the current thread if needed and returns the sleep duration in seconds.
        """
        target_cooldown = custom_cooldown if custom_cooldown is not None else self.get_cooldown(key)
        if target_cooldown <= 0:
            return 0.0

        sleep_time = 0.0
        with self._lock:
            now = time.time()
            last_time = self._last_request_times.get(key, 0.0)
            elapsed = now - last_time

            # Add small random jitter (e.g. 0.1s - 0.3s) to avoid bot detection via fixed periods
            jitter = random.uniform(self.jitter_range[0], self.jitter_range[1]) if self.jitter_range else 0.0
            required_interval = target_cooldown + jitter

            if elapsed < required_interval:
                sleep_time = required_interval - elapsed

            # Update next allowable timestamp
            self._last_request_times[key] = now + sleep_time

        if sleep_time > 0:
            logger.debug(f"[RateLimiter] Cooldown active for '{key}': sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)

        return sleep_time


# Global shared rate limiter singleton across source threads
global_rate_limiter = DomainRateLimiter(default_cooldown=1.0)
