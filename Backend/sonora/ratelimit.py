"""Rate limiting (moving window) on top of the ``limits`` library.

In-memory storage is per process, which is fine for local development. Deployments with
several API processes point ``SONORA_RATE_LIMIT_STORAGE_URL`` at Valkey/Redis so every
process shares the same counters.
"""

import math
import time

from limits import RateLimitItem, parse
from limits.aio.strategies import MovingWindowRateLimiter
from limits.storage import storage_from_string

from sonora.errors import RateLimited


class RateLimiter:
    def __init__(self, storage_url: str, *, enabled: bool = True) -> None:
        if not storage_url.startswith("async+"):
            storage_url = f"async+{storage_url}"
        self._storage = storage_from_string(storage_url)
        self._limiter = MovingWindowRateLimiter(self._storage)
        self.enabled = enabled

    async def hit(
        self, rule: str, *key: str, message: str | None = None, code: str | None = None
    ) -> None:
        """Consumes one request for ``key``; raises RateLimited when the limit is used up."""
        if not self.enabled:
            return
        item = parse(rule)
        if not await self._limiter.hit(item, *key):
            retry_after = await self._retry_after(item, key)
            raise RateLimited(message, code=code, headers={"Retry-After": str(retry_after)})

    async def allows(self, rule: str, *key: str) -> bool:
        """True if one more request would be allowed (does not consume anything)."""
        return not self.enabled or await self._limiter.test(parse(rule), *key)

    async def retry_after(self, rule: str, *key: str) -> int:
        return await self._retry_after(parse(rule), key)

    async def reset(self, rule: str, *key: str) -> None:
        await self._limiter.clear(parse(rule), *key)

    async def _retry_after(self, item: RateLimitItem, key: tuple[str, ...]) -> int:
        stats = await self._limiter.get_window_stats(item, *key)
        return max(1, math.ceil(stats.reset_time - time.time()))
