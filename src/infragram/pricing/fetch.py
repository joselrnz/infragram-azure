"""Price data from the network, kept a day.

Prices are fetched when an export runs, never when a page is opened. A body
fetched once is kept in the Infragram cache (``<cache>/pricing``) for a day,
so a set of diagrams, or the same one exported again, reads the network once.
"""

from __future__ import annotations

import gzip
import hashlib
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from ..iso3d.cache import cache_root
from . import PricingError

__all__ = ["KEEP", "cached_fetch", "fetch_url"]

#: How long a fetched body is reused, in seconds.
KEEP = 24 * 3600
_TIMEOUT = 30


def fetch_url(url: str) -> bytes:
    """The body at *url*, decompressed when it came gzipped. Prices are read
    over https and nothing else: a file: or ftp: URL is refused."""
    if urllib.parse.urlsplit(url).scheme != "https":
        raise PricingError(f"prices are read over https only, not {url}")
    request = urllib.request.Request(  # noqa: S310 - https, checked above
        url,
        headers={
            "User-Agent": "infragram (price at export)",
            "Accept-Encoding": "gzip",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310 - fixed https URLs
            body = response.read()
        return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
    except urllib.error.HTTPError as error:
        # an answer, not a missing network: the file moved, or was refused
        raise PricingError(f"{url} answered HTTP {error.code}") from error
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        EOFError,
        http.client.HTTPException,
    ) as error:
        raise PricingError(f"could not read {url}: {getattr(error, 'reason', error)}") from error


def cached_fetch(url: str) -> bytes:
    """:func:`fetch_url`, through the cache."""
    folder = cache_root() / "pricing"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:32] + ".bin")
    if path.is_file() and time.time() - path.stat().st_mtime < KEEP:
        return path.read_bytes()
    body = fetch_url(url)
    try:
        json.loads(body)
    except ValueError as error:
        # a captive portal's page or a cut-off file is not kept for a day
        raise PricingError(f"{url} did not answer with JSON ({error})") from error
    partial = path.with_name(f"{path.name}.{os.getpid()}.part")
    partial.write_bytes(body)
    os.replace(partial, path)
    return body
