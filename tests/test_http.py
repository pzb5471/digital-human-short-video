import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dhsv.http import request_with_retry


class Response:
    def __init__(self, status_code):
        self.status_code = status_code


class Session:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url))
        return Response(self.statuses.pop(0))

    def post(self, url, **kwargs):
        self.calls.append(("post", url))
        return Response(self.statuses.pop(0))


class HttpRetryTests(unittest.TestCase):
    def test_safe_get_retries_transient_status(self):
        session = Session([503, 200])
        self.assertEqual(
            200,
            request_with_retry(session, "get", "https://example.test", retries=2).status_code,
        )
        self.assertEqual(2, len(session.calls))

    def test_paid_post_is_never_automatically_retried(self):
        session = Session([503, 200])
        self.assertEqual(
            503,
            request_with_retry(session, "post", "https://example.test", retries=3).status_code,
        )
        self.assertEqual(1, len(session.calls))


if __name__ == "__main__":
    unittest.main()
