from .fake import FakeProvider
class HeyGenProvider(FakeProvider):
 name="heygen"
 def __init__(self,env,watermark_free_confirmed=False,session=None): super().__init__(watermark_free_confirmed); self.env=env; self.session=session
 def validate_credentials(self):
  return super().validate_credentials() if self.env.get("HEYGEN_API_KEY") else type(super().validate_credentials())(False,"missing HEYGEN_API_KEY")
