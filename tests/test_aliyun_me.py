import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dhsv.providers.aliyun_me import AliyunMEProvider
class AliyunTests(unittest.TestCase):
 def test_watermark_capability_fails_closed(self):
  self.assertFalse(AliyunMEProvider({}, watermark_free_confirmed=False).validate_credentials().available)
