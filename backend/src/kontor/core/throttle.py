"""Small in-memory limiter for failed attempts (login, invite codes).

State lives in the process, which is enough for the single API container of a homelab. It is
cleared on restart and is not shared between workers.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable


class Throttle:
    """Allows ``limit`` failures per key within ``window`` seconds, then blocks the key."""

    def __init__(
        self, limit: int, window: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        q = self._failures[key]
        cutoff = self._clock() - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        if not q:
            self._failures.pop(key, None)
            return deque()
        return q

    def retry_after(self, key: str) -> int:
        """Seconds until the key may try again; 0 when it is not blocked."""
        q = self._prune(key)
        if len(q) < self.limit:
            return 0
        return max(1, int(q[0] + self.window - self._clock()) + 1)

    def fail(self, key: str) -> None:
        self._prune(key)
        self._failures[key].append(self._clock())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)

    def clear(self) -> None:
        self._failures.clear()
