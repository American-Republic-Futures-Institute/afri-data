"""Bounded HTTPS source acquisition. No caller-controlled hosts or redirects."""
from __future__ import annotations
from hashlib import sha256
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.error import URLError, HTTPError


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Publisher redirect rejected")


def download_official(url: str, *, host: str, limit: int, opener=None) -> bytes:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != host or parsed.username
            or parsed.password or parsed.fragment or parsed.port is not None
            or not parsed.path.startswith("/")):
        raise ValueError("Unapproved official source location")
    if not 0 < limit <= 30_000_000:
        raise ValueError("Invalid download size ceiling")
    handler = opener or build_opener(NoRedirects())
    request = Request(url, headers={
        "User-Agent": "ARFI-Public-Evidence/1.0 (research reproduction)",
        "Accept": "application/json,text/plain,text/tab-separated-values,*/*",
        "Accept-Encoding": "identity",
    })
    try:
        with handler.open(request, timeout=35) as response:
            if response.geturl() != url:
                raise ValueError("Publisher redirect rejected")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > limit:
                raise ValueError("Official source exceeds size ceiling")
            payload = response.read(limit + 1)
            if not payload or len(payload) > limit:
                raise ValueError("Official source empty or oversized")
            return payload
    except (HTTPError, URLError, OSError) as exc:
        # NEVER interpolate exc: HTTPError can contain URL query secrets.
        raise RuntimeError("Official source download failed; check publisher status") from None


def fingerprint(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def post_official_json(url: str, payload: bytes, *, host: str,
                       limit: int, opener=None) -> bytes:
    """POST only deterministic JSON to one approved HTTPS publisher endpoint.

    A request is archived independently, while only the exact response is
    marked as publisher evidence. Fail closed for redirects and oversized
    responses. Never echo URL/credentials in exceptions.
    """
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != host or parsed.username
            or parsed.password or parsed.port is not None or parsed.query
            or parsed.fragment or not parsed.path.startswith("/")):
        raise ValueError("Unapproved official POST location")
    if (not isinstance(payload, bytes) or not 2 <= len(payload) <= 40_000
            or not 0 < limit <= 5_000_000):
        raise ValueError("Invalid source request or response size ceiling")
    try:
        import json
        request_doc = json.loads(payload.decode("utf-8"))
        if not isinstance(request_doc, dict):
            raise ValueError("POST body must be a JSON object")
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid published source request JSON") from None
    request = Request(url, data=payload, method="POST", headers={
        "User-Agent": "ARFI-Public-Evidence/1.0 (research reproduction)",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Content-Type": "application/json; charset=utf-8",
    })
    handler = opener or build_opener(NoRedirects())
    try:
        with handler.open(request, timeout=35) as response:
            if response.geturl() != url:
                raise ValueError("Publisher redirect rejected")
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) > limit:
                raise ValueError("Official response exceeds size ceiling")
            answer = response.read(limit + 1)
            if not answer or len(answer) > limit:
                raise ValueError("Official response empty or oversized")
            return answer
    except (HTTPError, URLError, OSError):
        raise RuntimeError("Official POST acquisition failed; check publisher status") from None
