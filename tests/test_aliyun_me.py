import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from alibabacloud_intelligentcreation20240313 import models as aliyun_models

from dhsv.models import JobState
from dhsv.providers.aliyun_me import AliyunMEProvider
from dhsv.providers.base import AvatarRef, ProviderValidationError, VideoRequest
from dhsv.providers.fake import FakeProvider
from dhsv.providers import oss_assets


def env(**changes):
    values = {
        "ALIBABA_CLOUD_ACCESS_KEY_ID": "ak",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "sk",
        "ALIYUN_OSS_ENDPOINT": "https://oss-cn-test.aliyuncs.com",
        "ALIYUN_OSS_BUCKET": "user-bucket",
    }
    values.update(changes)
    return values


def state() -> JobState:
    return JobState("demo", "aliyun-me", "approved", None, "idem", "script", "audio", "3.00", "now", "now")


class FakeAliyunClient:
    def __init__(self, *, resource_seconds=60, statuses=None):
        self.resource_seconds = resource_seconds
        self.statuses = list(statuses or [("RUNNING", None), ("SUCCESS", "https://download.example/result.mp4")])
        self.select_requests = []
        self.create_requests = []
        self.submit_requests = []
        self.get_requests = []

    def select_resource(self, request):
        self.select_requests.append(request)
        resource = aliyun_models.SelectResourceResponseBodyResourceInfoList().from_map(
            {"remainCount": self.resource_seconds, "unit": "second", "resourceType": 1}
        )
        body = aliyun_models.SelectResourceResponseBody(resource_info_list=[resource])
        return aliyun_models.SelectResourceResponse(body=body)

    def create_anchor(self, request):
        self.create_requests.append(request)
        body = aliyun_models.CreateAnchorResponseBody(data="anchor-new", success=True)
        return aliyun_models.CreateAnchorResponse(body=body)

    def submit_project_task(self, request):
        self.submit_requests.append(request)
        body = aliyun_models.SubmitProjectTaskResponseBody(task_id="task-123")
        return aliyun_models.SubmitProjectTaskResponse(body=body)

    def get_project_task(self, request):
        self.get_requests.append(request)
        status, url = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        body = aliyun_models.GetProjectTaskResponseBody(
            status=status,
            video_download_url=url,
            request_id="request-1",
            video_duration=30,
        )
        return aliyun_models.GetProjectTaskResponse(body=body)


class FailingCreateClient(FakeAliyunClient):
    def __init__(self, events):
        super().__init__()
        self.events = events

    def create_anchor(self, request):
        self.create_requests.append(request)
        self.events.append("create_anchor")
        raise RuntimeError("injected CreateAnchor failure")


class FailingSubmitClient(FakeAliyunClient):
    def __init__(self, events):
        super().__init__()
        self.events = events

    def submit_project_task(self, request):
        self.submit_requests.append(request)
        self.events.append("submit_project_task")
        raise RuntimeError("injected SubmitProjectTask failure")


class StubPublisher:
    def __init__(self):
        self.calls = []

    def publish(self, project_id, path):
        self.calls.append((project_id, Path(path)))
        name = Path(path).name
        return oss_assets.PublishedAsset(
            f"{project_id}/random-{name}",
            f"https://user-bucket.oss-cn-test.aliyuncs.com/{project_id}/random-{name}?Signature=secret",
        )


class FakeDownloadResponse:
    status_code = 200
    content = b"aliyun-video"


class FakeDownloadSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeDownloadResponse()


class FakeBucket:
    def __init__(self, signed_url="https://bucket.example/object?Signature=secret"):
        self.signed_url = signed_url
        self.put_calls = []
        self.sign_calls = []

    def put_object_from_file(self, key, filename):
        self.put_calls.append((key, filename))

    def sign_url(self, method, key, expires):
        self.sign_calls.append((method, key, expires))
        return self.signed_url


class OSSAssetPublisherTests(unittest.TestCase):
    def test_requires_all_credentials_user_bucket_and_https_endpoint(self):
        required = (
            "ALIBABA_CLOUD_ACCESS_KEY_ID",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
            "ALIYUN_OSS_ENDPOINT",
            "ALIYUN_OSS_BUCKET",
        )
        for missing in required:
            with self.subTest(missing=missing), self.assertRaises(ProviderValidationError):
                oss_assets.OSSAssetPublisher(env(**{missing: ""}), bucket=FakeBucket())
        with self.assertRaises(ProviderValidationError):
            oss_assets.OSSAssetPublisher(
                env(ALIYUN_OSS_ENDPOINT="http://oss-cn-test.aliyuncs.com"), bucket=FakeBucket()
            )

    def test_upload_uses_project_random_key_24h_https_and_key_only_public_state(self):
        bucket = FakeBucket("https://bucket.example/demo/token-portrait.png?Signature=secret")
        publisher = oss_assets.OSSAssetPublisher(
            env(), bucket=bucket, token_factory=lambda: "token"
        )
        with tempfile.TemporaryDirectory() as directory:
            portrait = Path(directory) / "portrait.png"
            portrait.write_bytes(b"portrait")
            artifact = publisher.publish("demo", portrait)
        self.assertEqual("demo/token-portrait.png", artifact.object_key)
        self.assertEqual(("GET", artifact.object_key, 86400), bucket.sign_calls[0])
        self.assertEqual({"object_key": artifact.object_key}, artifact.public_state)
        self.assertNotIn("Signature", repr(artifact))

    def test_rejects_non_https_signed_url(self):
        publisher = oss_assets.OSSAssetPublisher(
            env(), bucket=FakeBucket("http://bucket.example/object?Signature=secret")
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portrait.png"
            path.write_bytes(b"portrait")
            with self.assertRaises(ProviderValidationError):
                publisher.publish("demo", path)


class AliyunMEProviderTests(unittest.TestCase):
    def request(self, directory, *, digest=None, duration=30):
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
            duration,
        )

    def provider(self, client=None, publisher=None, **kwargs):
        client = client or FakeAliyunClient()
        captured = {}

        def factory(config):
            captured["config"] = config
            return client

        provider = AliyunMEProvider(
            env(),
            watermark_free_confirmed=True,
            client_factory=factory,
            asset_publisher=publisher or StubPublisher(),
            **kwargs,
        )
        return provider, client, captured

    def test_credentials_and_watermark_capability_fail_closed(self):
        self.assertFalse(issubclass(AliyunMEProvider, FakeProvider))
        self.assertFalse(AliyunMEProvider({}, watermark_free_confirmed=True).validate_credentials().available)
        self.assertFalse(AliyunMEProvider(env(), watermark_free_confirmed=False).validate_credentials().available)

    def test_default_endpoint_is_passed_to_injected_official_client_factory(self):
        provider, _, captured = self.provider()
        provider.get_status("task-123")
        config = captured["config"]
        self.assertEqual("ak", config.access_key_id)
        self.assertEqual("sk", config.access_key_secret)
        self.assertEqual("intelligentcreation.cn-zhangjiakou.aliyuncs.com", config.endpoint)

    def test_portrait_hash_mapping_reuses_anchor_without_publish_or_create(self):
        publisher = StubPublisher()
        provider, client, _ = self.provider(
            publisher=publisher,
            portrait_anchor_map={hashlib.sha256(b"portrait").hexdigest(): "anchor-cached"},
        )
        with tempfile.TemporaryDirectory() as directory:
            avatar = provider.create_or_reuse_avatar(self.request(directory), state())
        self.assertEqual("anchor-cached", avatar.id)
        self.assertEqual([], publisher.calls)
        self.assertEqual([], client.create_requests)

    def test_missing_mapping_publishes_portrait_and_creates_anchor_with_real_model(self):
        mapping = {}
        publisher = StubPublisher()
        provider, client, _ = self.provider(
            publisher=publisher, portrait_anchor_map=mapping
        )
        with tempfile.TemporaryDirectory() as directory:
            avatar = provider.create_or_reuse_avatar(self.request(directory), state())
        self.assertEqual("anchor-new", avatar.id)
        payload = client.create_requests[0].to_map()
        self.assertEqual("https", payload["coverUrl"].split(":", 1)[0])
        self.assertEqual("demo/random-portrait.png", payload["videoOssKey"])
        self.assertEqual("anchor-new", mapping[hashlib.sha256(b"portrait").hexdigest()])
        self.assertEqual(
            {"object_key": "demo/random-portrait.png"},
            provider.state_artifacts["portrait"],
        )
        self.assertNotIn("Signature", repr(provider.state_artifacts))

    def test_portrait_object_key_is_checkpointed_before_create_anchor_failure(self):
        events = []
        provider, _, _ = self.provider(
            client=FailingCreateClient(events),
            checkpoint_sink=lambda snapshot: events.append(("checkpoint", snapshot)),
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "CreateAnchor"):
                provider.create_or_reuse_avatar(self.request(directory), state())
        self.assertEqual("checkpoint", events[0][0])
        self.assertEqual("demo/random-portrait.png", events[0][1]["portrait"]["object_key"])
        self.assertEqual("create_anchor", events[1])
        self.assertEqual(events[0][1], provider.checkpoint_state)
        self.assertNotIn("Signature", repr(provider.checkpoint_state))

    def test_insufficient_resource_seconds_stops_before_upload_or_submit(self):
        publisher = StubPublisher()
        provider, client, _ = self.provider(
            client=FakeAliyunClient(resource_seconds=29), publisher=publisher
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProviderValidationError):
                provider.submit_video(self.request(directory, duration=30), AvatarRef("anchor"), "idem")
        self.assertEqual([], publisher.calls)
        self.assertEqual([], client.submit_requests)

    def test_submit_uses_exact_sdk_payload_and_duplicate_key_never_resubmits(self):
        publisher = StubPublisher()
        provider, client, _ = self.provider(publisher=publisher)
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(directory)
            first = provider.submit_video(request, AvatarRef("anchor-1"), "idem")
            second = provider.submit_video(request, AvatarRef("anchor-1"), "idem")
        self.assertEqual(first, second)
        self.assertEqual("task-123", first.job_id)
        self.assertEqual(1, len(client.select_requests))
        self.assertEqual({"idempotentId": "idem"}, client.select_requests[0].to_map())
        self.assertEqual(1, len(client.submit_requests))
        payload = client.submit_requests[0].to_map()
        self.assertEqual("9:16", payload["scaleType"])
        self.assertEqual(0, payload["subtitleTag"])
        self.assertEqual(0, payload["transparentBackground"])
        self.assertEqual(1, len(payload["frames"]))
        frame = payload["frames"][0]
        self.assertEqual(
            [{"index": 0, "material": {"id": "anchor-1"}, "type": "ANCHOR"}],
            frame["layers"],
        )
        self.assertEqual("AUDIO", frame["videoScript"]["type"])
        self.assertTrue(frame["videoScript"]["audioUrl"].startswith("https://"))
        self.assertNotIn("WATERMARK", repr(payload).upper())
        self.assertEqual("task-123", provider.state_artifacts["task_id"])
        self.assertEqual(
            {"object_key": "demo/random-narration.wav"},
            provider.state_artifacts["audio"],
        )

    def test_audio_object_key_is_checkpointed_before_submit_project_task_failure(self):
        events = []
        provider, _, _ = self.provider(
            client=FailingSubmitClient(events),
            checkpoint_sink=lambda snapshot: events.append(("checkpoint", snapshot)),
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "SubmitProjectTask"):
                provider.submit_video(self.request(directory), AvatarRef("anchor"), "idem")
        checkpoint = next(event for event in events if isinstance(event, tuple))
        self.assertEqual(
            "demo/random-narration.wav", checkpoint[1]["audio"]["object_key"]
        )
        self.assertLess(events.index(checkpoint), events.index("submit_project_task"))
        self.assertEqual(checkpoint[1], provider.checkpoint_state)
        self.assertNotIn("Signature", repr(provider.checkpoint_state))

    def test_audio_hash_mismatch_stops_before_any_sdk_or_oss_mutation(self):
        publisher = StubPublisher()
        provider, client, _ = self.provider(publisher=publisher)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProviderValidationError):
                provider.submit_video(
                    self.request(directory, digest="wrong"), AvatarRef("anchor"), "idem"
                )
        self.assertEqual([], publisher.calls)
        self.assertEqual([], client.select_requests)

    def test_status_poll_uses_get_project_task_and_completed_result_downloads(self):
        session = FakeDownloadSession()
        provider, client, _ = self.provider(download_session=session)
        self.assertEqual("processing", provider.get_status("task-123").status)
        self.assertEqual("completed", provider.get_status("task-123").status)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "video.mp4"
            downloaded = provider.download_result("task-123", destination)
            self.assertEqual(destination, downloaded.path)
            self.assertEqual(b"aliyun-video", destination.read_bytes())
        self.assertEqual(
            [{"taskId": "task-123"}, {"taskId": "task-123"}],
            [request.to_map() for request in client.get_requests],
        )
        self.assertEqual("https://download.example/result.mp4", session.calls[0][0])


if __name__ == "__main__":
    unittest.main()
