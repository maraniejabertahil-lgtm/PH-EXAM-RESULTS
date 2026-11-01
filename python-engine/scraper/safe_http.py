from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class UnsafeRedirectError(ValueError):
    """Raised before following a redirect outside an approved HTTPS origin."""


def _origin_key(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeRedirectError("Redirects must remain on the approved HTTPS origin.")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise UnsafeRedirectError("Redirect target contains an invalid port.") from exc
    return parsed.hostname.lower(), port


class SameOriginRedirectHandler(HTTPRedirectHandler):
    def __init__(self, origin_url):
        super().__init__()
        self.allowed_origin = _origin_key(origin_url)

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        try:
            target_origin = _origin_key(new_url)
        except UnsafeRedirectError:
            raise
        if target_origin != self.allowed_origin:
            raise UnsafeRedirectError(
                "Redirect to a different host or port was blocked before following it."
            )
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def open_same_origin(request: Request, origin_url: str, timeout: int = 30):
    opener = build_opener(SameOriginRedirectHandler(origin_url))
    return opener.open(request, timeout=timeout)
