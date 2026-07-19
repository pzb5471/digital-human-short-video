import hashlib
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from alibabacloud_intelligentcreation20240313 import models as aliyun_models

from dhsv.models import CostLine, JobState
from dhsv.providers.aliyun_me import AliyunMEProvider
from dhsv.providers.base import (
    AvatarRef,
    DownloadedAsset,
    ProviderStatus,
    ProviderValidationError,
    SubmittedJob,
    VideoRequest,
)
from dhsv.providers.fake import FakeProvider
from dhsv.providers.heygen import HeyGenProvider
from dhsv.providers.oss_assets import PublishedAsset


def state(provider: str) -> JobState:
    return JobState("demo", provider, "approved", None, "idem", "script", "audio", "0", "now", "now")


class AliyunClient:
    def __init__(self):
        self.submit_requests = []
        self.statuses = ["PENDING", "RUNNING", "RUNNING", "SUCCESS"]

    def select_resource(self, request):
        resource = aliyun_models.SelectResourceResponseBodyResourceInfoList().from_map(
            {"remainCount": 60, "unit": "second", "resourceType": 1}
        )
        return aliyun_models.SelectResourceResponse(
            body=aliyun_models.SelectResourceResponseBody(resource_info_list=[resource])
        )

    def create_anchor(self, request):
        return aliyun_models.CreateAnchorResponse(
            body=aliyun_models.CreateAnchorResponseBody(data="anchor", success=True)
        )

    def submit_project_task(self, request):
        self.submit_requests.append(request)
        return aliyun_models.SubmitProjectTaskResponse(
            body=aliyun_models.SubmitProjectTaskResponseBody(task_id="aliyun-job")
        )

    def get_project_task(self, request):
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        url = "https://download.example/aliyun.mp4" if status == "SUCCESS" else None
        return aliyun_models.GetProjectTaskResponse(
            body=aliyun_models.GetProjectTaskResponseBody(
                status=status, video_download_url=url, request_id="request", video_duration=30
            )
        )


class Publisher:
    def publish(self, project_id, path):
        return PublishedAsset(
            f"{project_id}/random-{Path(path).name}",
            f"https://bucket.example/{project_id}/random-{Path(path).name}?Signature=secret",
        )


class Response:
    def __init__(self, payload=None, *, content=b"", status_code=200):
        self.payload = payload or {}
        self.content = content
        self.status_code = status_code

    def json(self):
        return self.payload


class DownloadSession:
    def get(self, url, **kwargs):
        return Response(content=b"aliyun-video")


class HeyGenSession:
    def __init__(self):
        self.video_posts = 0
        self.statuses = ["queued", "processing", "processing", "completed"]

    def post(self, url, **kwargs):
        if url.endswith("/v3/assets"):
            return Response({"data": {"id": "audio-asset", "created_at": "now"}})
        if url.endswith("/v3/videos"):
            self.video_posts += 1
            return Response({"data": {"id": "heygen-job", "created_at": "now"}})
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url, **kwargs):
        if url.startswith("https://cdn.example/"):
            return Response(content=b"heygen-video")
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        data = {"id": "heygen-job", "status": status}
        if status == "completed":
            data["video_url"] = "https://cdn.example/heygen.mp4?token=signed"
        return Response({"data": data})


@dataclass
class Scenario:
    name: str
    provider: object
    request: VideoRequest
    provider_state: JobState
    mutation_count: object
    expected_bytes: bytes


class ProviderContractTests(unittest.TestCase):
    def request(self, directory: str) -> VideoRequest:
        portrait = Path(directory) / "portrait.png"
        narration = Path(directory) / "narration.wav"
        portrait.write_bytes(b"portrait")
        narration.write_bytes(b"audio")
        return VideoRequest(
            "demo",
            portrait,
            narration,
            hashlib.sha256(b"audio").hexdigest(),
            "Demo title",
            duration_seconds=30,
        )

    def scenarios(self, directory):
        request = self.request(directory)
        fake = FakeProvider(
            watermark_free_confirmed=True,
            status_sequence=("queued", "processing", "completed"),
            result_bytes=b"fake-video",
        )
        aliyun_client = AliyunClient()
        aliyun = AliyunMEProvider(
            {
                "ALIBABA_CLOUD_ACCESS_KEY_ID": "ak",
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "sk",
                "ALIYUN_OSS_ENDPOINT": "https://oss-cn-test.aliyuncs.com",
                "ALIYUN_OSS_BUCKET": "user-bucket",
            },
            watermark_free_confirmed=True,
            client_factory=lambda config: aliyun_client,
            asset_publisher=Publisher(),
            portrait_anchor_map={hashlib.sha256(b"portrait").hexdigest(): "anchor"},
            download_session=DownloadSession(),
        )
        heygen_session = HeyGenSession()
        heygen = HeyGenProvider(
            {"HEYGEN_API_KEY": "key", "HEYGEN_AVATAR_ID": "avatar"},
            watermark_free_confirmed=True,
            session=heygen_session,
        )
        return (
            Scenario("fake", fake, request, state("fake"), lambda: len(fake.jobs), b"fake-video"),
            Scenario(
                "aliyun",
                aliyun,
                request,
                state("aliyun-me"),
                lambda: len(aliyun_client.submit_requests),
                b"aliyun-video",
            ),
            Scenario(
                "heygen",
                heygen,
                request,
                state("heygen"),
                lambda: heygen_session.video_posts,
                b"heygen-video",
            ),
        )

    def test_same_six_method_and_cost_contract_for_all_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            for scenario in self.scenarios(directory):
                with self.subTest(provider=scenario.name):
                    self.assertTrue(scenario.provider.validate_credentials().available)
                    for method in (
                        "validate_credentials",
                        "estimate_cost",
                        "create_or_reuse_avatar",
                        "submit_video",
                        "get_status",
                        "download_result",
                    ):
                        self.assertTrue(callable(getattr(scenario.provider, method)))
                    self.assertIsInstance(scenario.provider.estimate_cost(scenario.request), CostLine)
                    self.assertIsInstance(
                        scenario.provider.create_or_reuse_avatar(
                            scenario.request, scenario.provider_state
                        ),
                        AvatarRef,
                    )

    def test_same_idempotency_status_resume_and_download_contract_for_all_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            for scenario in self.scenarios(directory):
                with self.subTest(provider=scenario.name):
                    avatar = scenario.provider.create_or_reuse_avatar(
                        scenario.request, scenario.provider_state
                    )
                    first = scenario.provider.submit_video(
                        scenario.request, avatar, "same-key"
                    )
                    second = scenario.provider.submit_video(
                        scenario.request, avatar, "same-key"
                    )
                    self.assertIsInstance(first, SubmittedJob)
                    self.assertEqual(first, second)
                    self.assertEqual(1, scenario.mutation_count())
                    self.assertEqual(ProviderStatus("queued"), scenario.provider.get_status(first.job_id))
                    destination = Path(directory) / f"{scenario.name}.mp4"
                    with self.assertRaises(ProviderValidationError):
                        scenario.provider.download_result(first.job_id, destination)
                    observed = []
                    for _ in range(3):
                        status = scenario.provider.get_status(first.job_id)
                        observed.append(status.status)
                        if status.status == "completed":
                            break
                    self.assertIn("processing", observed)
                    self.assertEqual("completed", observed[-1])
                    self.assertEqual(
                        DownloadedAsset(destination),
                        scenario.provider.download_result(first.job_id, destination),
                    )
                    self.assertEqual(scenario.expected_bytes, destination.read_bytes())


if __name__ == "__main__":
    unittest.main()
