"""Three explicit backends, one GPU owner; leases last through streamed response cleanup."""
import asyncio
import time
from contextlib import asynccontextmanager

TARGETS = ('deepseek', 'qwen', 'glm')


class Controller:
    def __init__(self, backend, active='deepseek', ttl=900, clock=time.monotonic, default='deepseek'):
        if default not in TARGETS or active not in (*TARGETS, None): raise ValueError('unknown backend')
        self.backend, self.active, self.default, self.ttl, self.clock = backend, active, default, ttl, clock
        self.inflight = self.waiters = 0
        self.switching = False
        self.fault = None
        self.last_activity = clock()
        self.lock = asyncio.Lock()
        self.idle = asyncio.Condition()

    async def _change(self, target):
        if self.fault is not None: raise RuntimeError('switching stopped for operator diagnosis')
        self.switching = True
        try:
            async with self.idle:
                await self.idle.wait_for(lambda: self.inflight == 0)
            task = asyncio.create_task(self.backend.switch(target))
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                self.active = target
                raise
            self.active = target
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.active = None
            self.fault = type(exc).__name__
            # A failed GPU/native start must not launch another model or retry itself.
            raise
        finally:
            self.switching = False

    @asynccontextmanager
    async def lease(self, target, activity=True):
        if target not in (*TARGETS, None): raise ValueError('unknown backend')
        if self.fault is not None: raise RuntimeError('switching stopped for operator diagnosis')
        if self.waiters >= 16: raise RuntimeError('switcher queue full')
        self.waiters += 1
        try:
            async with self.lock:
                target = target or self.active or self.default
                if self.active != target: await self._change(target)
                async with self.idle: self.inflight += 1
        finally:
            self.waiters -= 1
        try:
            yield
        finally:
            async with self.idle:
                self.inflight -= 1
                if activity: self.last_activity = self.clock()
                self.idle.notify_all()

    async def expire(self):
        if self.fault or self.active in (None, self.default) or self.inflight or self.lock.locked(): return False
        if self.ttl <= 0 or self.clock() - self.last_activity < self.ttl: return False
        async with self.lock:
            if self.active not in (None, self.default) and not self.inflight and self.clock() - self.last_activity >= self.ttl:
                await self._change(self.default)
                return True
        return False
