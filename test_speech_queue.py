"""Slow synthesis must not turn obsolete hover requests into a backlog."""
import asyncio
from threading import Event
import unittest

from speech_queue import SpeechQueue, SpeechQueueFull, SpeechSuperseded


class SlowSpeech:
    def __init__(self):
        self.entered, self.release = Event(), Event()
        self.calls = []

    def generate(self, text, profile, rate):
        self.calls.append(text)
        if text == "block":
            self.entered.set()
            if not self.release.wait(3):
                raise TimeoutError("Test did not release synthesis")
        if text == "bad":
            raise ValueError("Cannot synthesize")
        return {"text": text}


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = SlowSpeech()
        self.queue = SpeechQueue(self.service)

    async def asyncTearDown(self):
        self.service.release.set()
        await self.queue.close()

    async def blocked(self):
        job = self.queue.submit("block")
        self.assertTrue(await asyncio.to_thread(self.service.entered.wait, 1))
        return job

    async def test_many_obsolete_hovers_never_reach_synthesis(self):
        first = await self.blocked()
        jobs = [self.queue.submit(f"hover {i}", priority="hover", client_id="a", sequence=i) for i in range(1, 31)]
        current = self.queue.submit("result", client_id="a", sequence=31)
        self.assertEqual(len(self.queue.waiting), 1)
        self.service.release.set()
        await first.future
        self.assertEqual(await current.future, {"text": "result"})
        self.assertEqual(self.service.calls, ["block", "result"])
        for job in jobs:
            with self.assertRaises(SpeechSuperseded):
                await job.future

    async def test_action_overtakes_other_clients_hover_and_background(self):
        first = await self.blocked()
        hover = self.queue.submit("hover", priority="hover", client_id="hover-client", sequence=1)
        background = self.queue.submit("preview", priority="background")
        action = self.queue.submit("harvest result", priority="action", client_id="player", sequence=1)
        self.service.release.set()
        await asyncio.gather(*(job.future for job in (first, hover, background, action)))
        self.assertEqual(self.service.calls, ["block", "harvest result", "hover", "preview"])

    async def test_delayed_cancel_does_not_cancel_the_new_sequence(self):
        first = await self.blocked()
        old = self.queue.submit("old", client_id="a", sequence=1)
        new = self.queue.submit("new", client_id="a", sequence=2)
        self.queue.supersede("a", 2)
        self.service.release.set()
        await first.future
        self.assertEqual((await new.future)["text"], "new")
        with self.assertRaises(SpeechSuperseded):
            await old.future

    async def test_late_old_request_is_rejected_without_synthesis(self):
        self.queue.supersede("a", 5)
        job = self.queue.submit("late", client_id="a", sequence=4)
        with self.assertRaises(SpeechSuperseded):
            await job.future
        self.assertEqual(self.service.calls, [])

    async def test_active_generation_can_finish_without_delivering_obsolete_audio(self):
        active = self.queue.submit("block", client_id="a", sequence=1)
        self.assertTrue(await asyncio.to_thread(self.service.entered.wait, 1))
        self.queue.supersede("a", 2)
        with self.assertRaises(SpeechSuperseded):
            await active.future
        next_job = self.queue.submit("new", client_id="a", sequence=2)
        self.service.release.set()
        self.assertEqual((await next_job.future)["text"], "new")
        self.assertEqual(self.service.calls, ["block", "new"])

    async def test_failure_does_not_block_the_next_request(self):
        bad = self.queue.submit("bad")
        good = self.queue.submit("good")
        with self.assertRaises(ValueError):
            await bad.future
        self.assertEqual((await good.future)["text"], "good")

    async def test_queue_capacity_is_bounded(self):
        await self.blocked()
        self.queue.capacity = 1
        self.queue.submit("waiting")
        with self.assertRaises(SpeechQueueFull):
            self.queue.submit("overflow")


if __name__ == "__main__":
    unittest.main()
