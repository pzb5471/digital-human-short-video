import hashlib, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dhsv.providers.base import VideoRequest, ProviderValidationError
from dhsv.providers.fake import FakeProvider

class ProviderContractTests(unittest.TestCase):
 def test_rejects_audio_hash_mismatch_and_unconfirmed_watermark(self):
  with tempfile.TemporaryDirectory() as d:
   audio=Path(d)/"narration.wav"; audio.write_bytes(b"audio")
   request=VideoRequest("p", Path("portrait.png"), audio, "bad", "title")
   with self.assertRaises(ProviderValidationError): FakeProvider(watermark_free_confirmed=True).submit_video(request, None, "key")
   request=VideoRequest("p", Path("portrait.png"), audio, hashlib.sha256(b"audio").hexdigest(), "title")
   with self.assertRaises(ProviderValidationError): FakeProvider(watermark_free_confirmed=False).submit_video(request, None, "key")
