from decimal import Decimal
from .base import *
class FakeProvider:
 name="fake"
 def __init__(self,watermark_free_confirmed=False): self.watermark_free_confirmed=watermark_free_confirmed; self.jobs={}
 def validate_credentials(self): return CapabilityReport(self.watermark_free_confirmed,"watermark-free capability unconfirmed" if not self.watermark_free_confirmed else "")
 def estimate_cost(self,r): return CostLine("Fake","CNY",Decimal("0"),"test")
 def create_or_reuse_avatar(self,r,s): return AvatarRef("fake-avatar")
 def submit_video(self,r,a,idempotency_key):
  validate_final_audio(r)
  if not self.validate_credentials().available: raise ProviderValidationError("watermark-free capability unconfirmed")
  self.jobs.setdefault(idempotency_key,SubmittedJob("fake-"+idempotency_key)); return self.jobs[idempotency_key]
 def get_status(self,j): return ProviderStatus("completed")
 def download_result(self,j,d): return DownloadedAsset(d)
