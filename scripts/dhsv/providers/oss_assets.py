import secrets
from pathlib import Path
class OSSPublisher:
 def __init__(self,bucket,endpoint,client): self.bucket,self.endpoint,self.client=bucket,endpoint,client
 def publish(self,project_id,path):
  key=f"{project_id}/{secrets.token_hex(12)}-{Path(path).name}"; self.client.put_object_from_file(key,str(path)); return key,self.client.sign_url("GET",key,86400)
