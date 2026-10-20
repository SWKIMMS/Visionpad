"""The async API preserves legacy callers and rejects obsolete browser requests."""
import unittest
from unittest.mock import patch

from fastapi import HTTPException
import game_app
from game_speech import SpeechUnavailable
from speech_queue import SpeechQueue


class FakeRequest:
    async def is_disconnected(self):
        return False


class FakeService:
    def __init__(self):
        self.calls = []

    def generate(self, text, profile, rate):
        self.calls.append(text)
        if text == 'unavailable':
            raise SpeechUnavailable('Voice unavailable')
        return {'text': text, 'profile': profile, 'rate': rate, 'url': '/audio.wav'}


class SpeechApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = FakeService()
        self.queue = SpeechQueue(self.service)
        self.patcher = patch.object(game_app, 'speech_jobs', self.queue)
        self.patcher.start()

    async def asyncTearDown(self):
        self.patcher.stop()
        await self.queue.close()

    async def test_legacy_request_still_generates_speech(self):
        result = await game_app.synthesize_speech(game_app.SpeechRequest(text='Hello.'), FakeRequest())
        self.assertEqual(result['text'], 'Hello.')

    async def test_partial_client_identity_is_rejected_before_generation(self):
        with self.assertRaises(HTTPException) as caught:
            await game_app.synthesize_speech(game_app.SpeechRequest(text='Hello.', client_id='browser'), FakeRequest())
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(self.service.calls, [])

    async def test_cancel_route_discards_old_request_but_accepts_current_one(self):
        result = await game_app.cancel_speech(game_app.SpeechCancelRequest(client_id='browser', sequence=5))
        self.assertEqual(result.status_code, 204)
        result = await game_app.synthesize_speech(game_app.SpeechRequest(text='Old.', client_id='browser', sequence=4), FakeRequest())
        self.assertEqual(result.status_code, 204)
        fresh = await game_app.synthesize_speech(game_app.SpeechRequest(text='Fresh.', client_id='browser', sequence=5), FakeRequest())
        self.assertEqual(fresh['text'], 'Fresh.')
        self.assertEqual(self.service.calls, ['Fresh.'])

    async def test_generation_error_keeps_503_and_the_queue_can_retry(self):
        with self.assertRaises(HTTPException) as caught:
            await game_app.synthesize_speech(game_app.SpeechRequest(text='unavailable'), FakeRequest())
        self.assertEqual(caught.exception.status_code, 503)
        result = await game_app.synthesize_speech(game_app.SpeechRequest(text='Retry.'), FakeRequest())
        self.assertEqual(result['text'], 'Retry.')


if __name__ == '__main__':
    unittest.main()
