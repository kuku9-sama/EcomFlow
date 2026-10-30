"""读取和显式幂等写入的有限重试客户端。"""

import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import requests

log = logging.getLogger(__name__)


class APIError(RuntimeError):
    """HTTP、传输或响应协议异常。"""


class AuthenticationError(APIError):
    """认证失败，不自动重试。"""


class APIClient:
    def __init__(
        self,
        base_url: str,
        session=None,
        retries: int = 2,
        timeout: tuple[float, float] = (2, 3),
        sleep=time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        # 本地模拟调用不需要代理认证。
        if session is None:
            from urllib.parse import urlparse

            if urlparse(base_url).hostname not in ("127.0.0.1", "localhost", "::1"):
                raise ValueError("Only local mock platform URLs are allowed")
        self.retries = retries
        self.timeout = timeout
        self.sleep = sleep

    def request(
        self,
        method: str,
        path: str,
        *,
        business_id: str = "",
        idempotency_key: str | None = None,
        **kwargs,
    ):
        """仅在操作可安全重复时重试临时故障。"""
        safe = method.upper() == "GET" or bool(idempotency_key)
        headers = dict(kwargs.pop("headers", {}))
        headers["X-Business-ID"] = business_id
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        for attempt in range(self.retries + 1):
            log.info(
                "request method=%s path=%s business_id=%s attempt=%s",
                method,
                path,
                business_id,
                attempt,
            )
            response = None
            try:
                response = self.session.request(
                    method,
                    self.base_url + path,
                    timeout=self.timeout,
                    headers=headers,
                    **kwargs,
                )
                if response.status_code == 401:
                    raise AuthenticationError("HTTP 401 authentication rejected")
                response.raise_for_status()
                try:
                    return response.json()
                except ValueError as exc:
                    raise APIError("Invalid JSON response") from exc
            except (
                requests.Timeout,
                requests.ConnectionError,
                requests.HTTPError,
            ) as exc:
                status = response.status_code if response is not None else None
                retryable = status in (429, 500, 502, 503, 504) or isinstance(
                    exc, (requests.Timeout, requests.ConnectionError)
                )
                if not safe or not retryable or attempt == self.retries:
                    raise APIError(
                        f"{type(exc).__name__}: HTTP {status or 'transport'}"
                    ) from exc
                delay = min(0.1 * 2**attempt, 2)
                retry_after = (
                    response.headers.get("Retry-After")
                    if response is not None
                    else None
                )
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        try:
                            delay = max(
                                delay,
                                (
                                    parsedate_to_datetime(retry_after)
                                    - datetime.now(timezone.utc)
                                ).total_seconds(),
                            )
                        except (ValueError, TypeError, OverflowError):
                            raise APIError("Invalid Retry-After") from exc
                    if delay > 10:
                        raise APIError(
                            "Retry-After exceeds automatic retry budget"
                        ) from exc
                self.sleep(delay)
        raise APIError("Retry budget exhausted")

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)
