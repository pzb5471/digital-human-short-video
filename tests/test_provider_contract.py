import hashlib
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dhsv.models import JobState
from dhsv.providers.base import (
    AvatarRef,
    DownloadedAsset,
    ProviderStatus,
    ProviderValidationError,
    SubmittedJob,
    VideoRequest,
)
from dhsv.providers.fake import FakeProvider


def state() -> JobState:
    return JobState("demo", "fake", "approved", None, "idem", "script", "audio", "0", "now", "now")


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

    def test_fake_implements_six_method_contract_and_zero_cost(self):
        provider = FakeProvider(watermark_free_confirmed=True)
        for method in (
            "validate_credentials",
            "estimate_cost",
            "create_or_reuse_avatar",
            "submit_video",
            "get_status",
            "download_result",
        ):
            self.assertTrue(callable(getattr(provider, method)))
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(directory)
            self.assertEqual(Decimal("0"), provider.estimate_cost(request).amount)
            self.assertIsInstance(provider.create_or_reuse_avatar(request, state()), AvatarRef)
            self.assertIsInstance(provider.submit_video(request, AvatarRef("avatar"), "idem"), SubmittedJob)

    def test_fake_status_sequence_is_controllable_and_download_requires_completion(self):
        provider = FakeProvider(
            watermark_free_confirmed=True,
            status_sequence=("queued", "processing", "completed"),
            result_bytes=b"video",
        )
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(directory)
            job = provider.submit_video(request, AvatarRef("avatar"), "idem")
            destination = Path(directory) / "result.mp4"
            with self.assertRaises(ProviderValidationError):
                provider.download_result(job.job_id, destination)
            self.assertEqual(ProviderStatus("queued"), provider.get_status(job.job_id))
            self.assertEqual(ProviderStatus("processing"), provider.get_status(job.job_id))
            self.assertEqual(ProviderStatus("completed"), provider.get_status(job.job_id))
            self.assertEqual(DownloadedAsset(destination), provider.download_result(job.job_id, destination))
            self.assertEqual(b"video", destination.read_bytes())

    def test_fake_duplicate_idempotency_key_never_creates_a_second_job(self):
        provider = FakeProvider(watermark_free_confirmed=True)
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(directory)
            first = provider.submit_video(request, AvatarRef("avatar"), "same-key")
            second = provider.submit_video(request, AvatarRef("avatar"), "same-key")
        self.assertEqual(first, second)
        self.assertEqual(1, len(provider.jobs))

    def test_rejects_audio_hash_mismatch_and_unconfirmed_watermark_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(directory)
            bad = VideoRequest(
                request.project_id,
                request.portrait_path,
                request.narration_path,
                "bad",
                request.title,
                request.duration_seconds,
            )
            provider = FakeProvider(watermark_free_confirmed=True)
            with self.assertRaises(ProviderValidationError):
                provider.submit_video(bad, AvatarRef("avatar"), "key")
            self.assertEqual(0, len(provider.jobs))
            with self.assertRaises(ProviderValidationError):
                FakeProvider(watermark_free_confirmed=False).submit_video(
                    request, AvatarRef("avatar"), "key"
                )


if __name__ == "__main__":
    unittest.main()
