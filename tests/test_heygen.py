import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dhsv.models import JobState
from dhsv.providers.base import AvatarRef, ProviderValidationError, VideoRequest
from dhsv.providers.fake import FakeProvider
from dhsv.providers.heygen import HeyGenProvider


def env(**changes):
    values = {"HEYGEN_API_KEY": "heygen-key"}
    values.update(changes)
    return values


def state() -> JobState:
    return JobState("demo", "heygen", "approved", None, "idem", "script", "audio", "1.50", "now", "now")


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, content=b""):
        self.payload = payload or {}
        self.status_code = status_code
        self.content = content

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, *, posts=None, gets=None, events=None):
        self.post_responses = list(posts or [])
        self.get_responses = list(gets or [])
        self.calls = []
        self.events = events

    def post(self, url, **kwargs):
        if self.events is not None:
            self.events.append(("post", url))
        captured = dict(kwargs)
        if "files" in captured:
            filename, handle, content_type = captured["files"]["file"]
            captured["files"] = {
                "file": {
                    "filename": filename,
                    "content": handle.read(),
                    "content_type": content_type,
                }
            }
        self.calls.append(("POST", url, captured))
        if not self.post_responses:
            raise AssertionError(f"unexpected POST {url}")
        return self.post_responses.pop(0)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, dict(kwargs)))
        if not self.get_responses:
            raise AssertionError(f"unexpected GET {url}")
        return self.get_responses.pop(0)


def response(identifier):
    return FakeResponse({"data": {"id": identifier, "created_at": "now"}})


class HeyGenProviderTests(unittest.TestCase):
    def request(self, directory, *, digest=None):
        portrait = Path(directory) / "portrait.png"
        narration = Path(directory) / "narration.wav"
        portrait.write_bytes(b"portrait")
        narration.write_bytes(b"audio")
        return VideoRequest(
            "demo",
            portrait,
            narration,
            digest or hashlib.sha256(b"audio").hexdigest(),
            "Demo title",
            30,
        )

    def test_real_adapter_does_not_inherit_fake_and_credentials_fail_closed(self):
        self.assertFalse(issubclass(HeyGenProvider, FakeProvider))
        self.assertFalse(HeyGenProvider({}, watermark_free_confirmed=True).validate_credentials().available)
        self.assertFalse(HeyGenProvider(env(), watermark_free_confirmed=False).validate_credentials().available)

    def test_cached_avatar_is_preferred_without_any_http_mutation(self):
        session = FakeSession()
        provider = HeyGenProvider(
            env(HEYGEN_AVATAR_ID="avatar-cached", HEYGEN_IMAGE_FALLBACK="true"),
            watermark_free_confirmed=True,
            session=session,
        )
        with tempfile.TemporaryDirectory() as directory:
            avatar = provider.create_or_reuse_avatar(self.request(directory), state())
        self.assertEqual("avatar-cached", avatar.id)
        self.assertEqual([], session.calls)
        self.assertEqual("avatar-cached", provider.state_artifacts["avatar_id"])

    def test_portrait_multipart_then_photo_avatar_mutation_are_idempotent_and_persist_ids(self):
        session = FakeSession(posts=[response("portrait-asset"), response("avatar-new")])
        provider = HeyGenProvider(
            env(), watermark_free_confirmed=True, session=session, avatar_cache={}
        )
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(directory)
            first = provider.create_or_reuse_avatar(request, state())
            second = provider.create_or_reuse_avatar(request, state())
        self.assertEqual(first, second)
        self.assertEqual("avatar-new", first.id)
        self.assertEqual(
            ["https://api.heygen.com/v3/assets", "https://api.heygen.com/v3/photo_avatars"],
            [call[1] for call in session.calls],
        )
        asset_call, avatar_call = session.calls
        self.assertEqual(b"portrait", asset_call[2]["files"]["file"]["content"])
        self.assertEqual("portrait.png", asset_call[2]["files"]["file"]["filename"])
        self.assertEqual(
            {"asset_id": "portrait-asset", "name": "Demo title"}, avatar_call[2]["json"]
        )
        for _, _, call in session.calls:
            self.assertTrue(call["headers"]["Idempotency-Key"])
        self.assertEqual("portrait-asset", provider.state_artifacts["portrait_asset_id"])
        self.assertEqual("avatar-new", provider.state_artifacts["avatar_id"])

    def test_explicit_image_fallback_uses_image_asset_in_video_payload(self):
        session = FakeSession(
            posts=[response("portrait-asset"), response("audio-asset"), response("video-1")]
        )
        provider = HeyGenProvider(
            env(HEYGEN_IMAGE_FALLBACK="true"),
            watermark_free_confirmed=True,
            session=session,
        )
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(directory)
            avatar = provider.create_or_reuse_avatar(request, state())
            provider.submit_video(request, avatar, "idem")
        self.assertEqual("portrait-asset", avatar.id)
        payload = session.calls[-1][2]["json"]
        self.assertEqual("image", payload["type"])
        self.assertEqual("portrait-asset", payload["image_asset_id"])
        self.assertNotIn("avatar_id", payload)

    def test_only_explicit_true_enables_image_fallback(self):
        for value in ("", "false", "1", "yes", "on"):
            with self.subTest(value=value):
                session = FakeSession(
                    posts=[response("portrait-asset"), response("avatar-new")]
                )
                provider = HeyGenProvider(
                    env(HEYGEN_IMAGE_FALLBACK=value),
                    watermark_free_confirmed=True,
                    session=session,
                )
                with tempfile.TemporaryDirectory() as directory:
                    avatar = provider.create_or_reuse_avatar(
                        self.request(directory), state()
                    )
                self.assertEqual("avatar-new", avatar.id)

    def test_audio_multipart_and_video_payload_are_exact_for_avatar_mode(self):
        session = FakeSession(posts=[response("audio-asset"), response("video-1")])
        provider = HeyGenProvider(
            env(HEYGEN_AVATAR_ID="avatar-cached"),
            watermark_free_confirmed=True,
            session=session,
        )
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(directory)
            avatar = provider.create_or_reuse_avatar(request, state())
            first = provider.submit_video(request, avatar, "idem")
            second = provider.submit_video(request, avatar, "idem")
        self.assertEqual(first, second)
        self.assertEqual("video-1", first.job_id)
        self.assertEqual(2, len(session.calls))
        upload, submit = session.calls
        self.assertEqual("https://api.heygen.com/v3/assets", upload[1])
        self.assertEqual(b"audio", upload[2]["files"]["file"]["content"])
        self.assertEqual("narration.wav", upload[2]["files"]["file"]["filename"])
        self.assertEqual("https://api.heygen.com/v3/videos", submit[1])
        self.assertEqual(
            {
                "type": "avatar",
                "avatar_id": "avatar-cached",
                "title": "Demo title",
                "resolution": "1080p",
                "aspect_ratio": "9:16",
                "fit": "contain",
                "audio_asset_id": "audio-asset",
                "output_format": "mp4",
            },
            submit[2]["json"],
        )
        for forbidden in ("script", "voice_id", "watermark"):
            self.assertNotIn(forbidden, submit[2]["json"])
        self.assertEqual("idem:audio", upload[2]["headers"]["Idempotency-Key"])
        self.assertEqual("idem", submit[2]["headers"]["Idempotency-Key"])
        self.assertEqual("audio-asset", provider.state_artifacts["audio_asset_id"])
        self.assertEqual("video-1", provider.state_artifacts["video_id"])

    def test_audio_asset_id_is_checkpointed_before_video_submit_failure(self):
        events = []
        session = FakeSession(
            posts=[response("audio-asset"), FakeResponse(status_code=500)], events=events
        )
        provider = HeyGenProvider(
            env(HEYGEN_AVATAR_ID="avatar-cached"),
            watermark_free_confirmed=True,
            session=session,
            checkpoint_sink=lambda snapshot: events.append(("checkpoint", snapshot)),
        )
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(directory)
            avatar = provider.create_or_reuse_avatar(request, state())
            with self.assertRaisesRegex(ProviderValidationError, "video submission"):
                provider.submit_video(request, avatar, "idem")
        audio_checkpoint = next(
            event
            for event in events
            if event[0] == "checkpoint" and "audio_asset_id" in event[1]
        )
        video_post = ("post", "https://api.heygen.com/v3/videos")
        self.assertLess(events.index(audio_checkpoint), events.index(video_post))
        self.assertEqual("audio-asset", provider.checkpoint_state["audio_asset_id"])
        self.assertNotIn("video_url", provider.checkpoint_state)
        self.assertNotIn("heygen-key", repr(provider.checkpoint_state))

    def test_hash_and_watermark_failures_happen_before_http_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            bad_session = FakeSession()
            request = self.request(directory, digest="wrong")
            with self.assertRaises(ProviderValidationError):
                HeyGenProvider(
                    env(), watermark_free_confirmed=True, session=bad_session
                ).submit_video(request, AvatarRef("avatar"), "idem")
            self.assertEqual([], bad_session.calls)
            closed_session = FakeSession()
            with self.assertRaises(ProviderValidationError):
                HeyGenProvider(
                    env(), watermark_free_confirmed=False, session=closed_session
                ).submit_video(
                    VideoRequest(
                        request.project_id,
                        request.portrait_path,
                        request.narration_path,
                        hashlib.sha256(b"audio").hexdigest(),
                        request.title,
                        request.duration_seconds,
                    ),
                    AvatarRef("avatar"),
                    "idem",
                )
            self.assertEqual([], closed_session.calls)

    def test_poll_only_uses_video_id_endpoint_then_downloads_completed_https_result(self):
        session = FakeSession(
            gets=[
                FakeResponse({"data": {"id": "video-1", "status": "processing"}}),
                FakeResponse(
                    {
                        "data": {
                            "id": "video-1",
                            "status": "completed",
                            "video_url": "https://cdn.example/video-1.mp4?token=secret",
                        }
                    }
                ),
                FakeResponse(content=b"heygen-video"),
            ]
        )
        provider = HeyGenProvider(env(), watermark_free_confirmed=True, session=session)
        self.assertEqual("processing", provider.get_status("video-1").status)
        self.assertEqual("completed", provider.get_status("video-1").status)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "result.mp4"
            provider.download_result("video-1", destination)
            self.assertEqual(b"heygen-video", destination.read_bytes())
        self.assertEqual(
            [
                "https://api.heygen.com/v3/videos/video-1",
                "https://api.heygen.com/v3/videos/video-1",
                "https://cdn.example/video-1.mp4?token=secret",
            ],
            [call[1] for call in session.calls],
        )
        self.assertTrue(all(call[0] == "GET" for call in session.calls))
        self.assertNotIn("video_url", provider.state_artifacts)
        self.assertNotIn("token=secret", repr(provider.state_artifacts))


if __name__ == "__main__":
    unittest.main()
