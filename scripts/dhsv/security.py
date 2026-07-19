import re


def redact(value: str) -> str:
    value = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)\b(AK|SK|API[_-]?KEY|ACCESS[_-]?KEY(?:[_-]?SECRET)?)=([^\s&]+)", r"\1=[REDACTED]", value)
    value = re.sub(r"(?i)(Signature=)[^&#\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(OSSAccessKeyId=)[^&#\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"https?://[^\s?]+\.oss-[^\s?]+\.aliyuncs\.com/[^\s?]+\?[^\s]+", "[REDACTED_OSS_SIGNED_URL]", value)
    return value
