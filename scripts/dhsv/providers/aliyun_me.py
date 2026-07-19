from .fake import FakeProvider
class AliyunMEProvider(FakeProvider):
 name="aliyun-me"
 def __init__(self,env,watermark_free_confirmed=False,client_factory=None): super().__init__(watermark_free_confirmed); self.env=env; self.client_factory=client_factory
 def validate_credentials(self):
  keys=("ALIBABA_CLOUD_ACCESS_KEY_ID","ALIBABA_CLOUD_ACCESS_KEY_SECRET","ALIYUN_OSS_ENDPOINT","ALIYUN_OSS_BUCKET")
  return super().validate_credentials() if all(self.env.get(k) for k in keys) else type(super().validate_credentials())(False,"missing Aliyun credentials")
