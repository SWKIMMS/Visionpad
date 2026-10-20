"""One synthesis at a time; obsolete queued lines never reach Piper."""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass


class SpeechSuperseded(Exception):
    pass


class SpeechQueueFull(Exception):
    pass


@dataclass
class SpeechJob:
    text: str
    profile: str
    rate: float
    priority: int
    client_id: str | None
    sequence: int
    future: asyncio.Future


class SpeechQueue:
    PRIORITIES = {"action": 0, "dialogue": 0, "hover": 1, "background": 2}

    def __init__(self, service, capacity=64):
        self.service = service
        self.capacity = capacity
        self.waiting = []
        self.latest = OrderedDict()
        self.current = None
        self.worker = None
        self.wake = asyncio.Event()

    def supersede(self, client_id, sequence):
        self.latest[client_id] = max(sequence, self.latest.get(client_id, 0))
        self.latest.move_to_end(client_id)
        for job in list(self.waiting) + ([self.current] if self.current else []):
            if job.client_id == client_id and job.sequence < self.latest[client_id]:
                self.cancel(job)
        while len(self.latest) > 512:
            self.latest.popitem(last=False)

    def cancel(self, job):
        if job in self.waiting:
            self.waiting.remove(job)
        if not job.future.done():
            job.future.set_exception(SpeechSuperseded())

    def submit(self, text, profile="system", rate=1.0, priority="action", client_id=None, sequence=0):
        if client_id:
            self.supersede(client_id, sequence)
        future = asyncio.get_running_loop().create_future()
        # A disconnected request may no longer have a waiter to retrieve errors.
        future.add_done_callback(lambda result: result.exception() if not result.cancelled() else None)
        job = SpeechJob(text, profile, rate, self.PRIORITIES[priority], client_id, sequence, future)
        if client_id and sequence < self.latest[client_id]:
            self.cancel(job)
            return job
        if len(self.waiting) >= self.capacity:
            raise SpeechQueueFull("Speech is busy. Click Replay to retry.")
        self.waiting.append(job)
        self.wake.set()
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self.run())
        return job

    async def run(self):
        while True:
            await self.wake.wait()
            if not self.waiting:
                self.wake.clear()
                continue
            # min preserves arrival order among equally important results/dialogue.
            job = min(self.waiting, key=lambda entry: entry.priority)
            self.waiting.remove(job)
            self.current = job
            try:
                result = await asyncio.to_thread(self.service.generate, job.text, job.profile, job.rate)
                if not job.future.done():
                    job.future.set_result(result)
            except Exception as error:
                if not job.future.done():
                    job.future.set_exception(error)
            finally:
                self.current = None

    async def close(self):
        for job in list(self.waiting) + ([self.current] if self.current else []):
            self.cancel(job)
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        self.worker = None
        self.wake = asyncio.Event()
