import time


def request_with_retry(session, method, url, *, retries=3, **kwargs):
    for attempt in range(retries):
        response = getattr(session, method)(url, **kwargs)
        if response.status_code not in {429, 500, 502, 503, 504} or attempt == retries - 1:
            return response
        time.sleep(min(2 ** attempt, 4))
