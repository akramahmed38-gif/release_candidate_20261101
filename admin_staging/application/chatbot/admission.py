"""Bounded chat admission with per-user isolation and cancellation-safe release."""
from contextlib import asynccontextmanager
import asyncio


class AdmissionBusy(Exception):pass


class RequestAdmission:
    def __init__(self,workers=8,max_pending=4096,wait_seconds=15):
        self.slots=asyncio.Semaphore(workers)
        self.max_pending=max_pending
        self.wait_seconds=wait_seconds
        self.pending=0
        self.users=set()

    @asynccontextmanager
    async def acquire(self,identity):
        if self.pending>=self.max_pending or identity in self.users:raise AdmissionBusy()
        self.pending+=1
        self.users.add(identity)
        acquired=False
        try:
            try:
                await asyncio.wait_for(self.slots.acquire(),timeout=self.wait_seconds)
                acquired=True
            except asyncio.TimeoutError:
                raise AdmissionBusy() from None
            yield
        finally:
            if acquired:self.slots.release()
            self.pending-=1
            self.users.discard(identity)
