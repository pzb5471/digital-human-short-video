import time


def request_with_retry(session, method, url, *, retries=3, **kwargs):
    method = str(method).lower()
    attempts = retries if method in {"get", "head"} else 1
    for attempt in range(attempts):
        response = getattr(session, method)(url, **kwargs)
        if response.status_code not in {429, 500, 502, 503, 504} or attempt == attempts - 1:
            return response
        time.sleep(min(2 ** attempt, 4))
