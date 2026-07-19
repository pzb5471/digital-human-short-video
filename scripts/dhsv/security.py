import re


def redact(value: str) -> str:
    value = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", value)
    value = re.sub(
        r"(?i)\b(HEYGEN_API_KEY|ALIBABA_CLOUD_ACCESS_KEY_ID|ALIBABA_CLOUD_ACCESS_KEY_SECRET|X-API-KEY|AK|SK|API[_-]?KEY|ACCESS[_-]?KEY(?:[_-]?(?:ID|SECRET))?)\s*[:=]\s*([^\s&]+)",
        r"\1=[REDACTED]",
        value,
    )
    value = re.sub(r"(?i)(Signature=)[^&#\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(OSSAccessKeyId=)[^&#\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"https?://[^\s?]+\.oss-[^\s?]+\.aliyuncs\.com/[^\s?]+\?[^\s]+", "[REDACTED_OSS_SIGNED_URL]", value)
    return value
