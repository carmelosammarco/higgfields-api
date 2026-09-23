from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from .client import HiggsfieldError


CATALOG_URL = "https://console.higgsfield.ai/"
CATALOG_API_URL = "https://dash.higgsfield.ai/api/v2/catalog-models/?page_size=15"


def fetch_catalog(*, transport: Optional[httpx.BaseTransport] = None) -> Dict[str, Any]:
    """Read the public console catalog without sending account credentials.

    This is a console-facing feed, not a documented stable generation API.
    Validate pagination and disclose any server count discrepancy.
    """
    url = CATALOG_API_URL
    seen = set()
    entries = {}
    count = None
    with httpx.Client(timeout=30, transport=transport, follow_redirects=False) as client:
        while url:
            parsed = urlparse(url)
            if (parsed.scheme != "https" or parsed.netloc != "dash.higgsfield.ai"
                    or parsed.path != "/api/v2/catalog-models/" or url in seen):
                raise HiggsfieldError("Invalid or repeated catalog pagination URL")
            if len(seen) >= 100:
                raise HiggsfieldError("Catalog pagination exceeded 100 pages")
            seen.add(url)
            try:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise HiggsfieldError("Live catalog unavailable; use models --starters or the console") from exc
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise HiggsfieldError("Catalog schema changed: missing results")
            if type(data.get("count")) is not int or data["count"] < 0:
                raise HiggsfieldError("Catalog schema changed: invalid count")
            if count is not None and count != data["count"]:
                raise HiggsfieldError("Catalog changed during pagination; retry discovery")
            count = data["count"]
            for item in data["results"]:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    raise HiggsfieldError("Catalog schema changed: invalid entry")
                entries[item["id"]] = item
            url = data.get("next")
            if url is not None and not isinstance(url, str):
                raise HiggsfieldError("Catalog schema changed: invalid next link")
    return {"source": CATALOG_API_URL, "catalog": CATALOG_URL,
            "count": len(entries), "advertised_count": count,
            "count_matches": len(entries) == count,
            "warnings": [] if len(entries) == count else [
                "Server advertised a different total; all supplied pages were read, but completeness cannot be confirmed"],
            "models": list(entries.values()),
            "scope": "Public catalog families/workflows, not every mode or account entitlement",
            "pricing_note": "Public indicative pricing; estimate exact parameters with your account"}

# A small set of documented starters. The generic CLI accepts every endpoint ID,
# including models added after this package release.
STARTERS: Dict[str, Dict[str, Any]] = {
    "soul": {
        "endpoint": "higgsfield-ai/soul/v2/standard",
        "kind": "text-to-image",
        "example": {"prompt": "Editorial portrait in soft daylight"},
    },
    "seedance-2-text": {
        "endpoint": "bytedance/seedance-2.0/text-to-video",
        "kind": "text-to-video",
        "example": {
            "prompt": "A cinematic tracking shot along a sunlit coastal road",
            "resolution": "720p",
            "generate_audio": True,
            "duration": 5,
            "aspect_ratio": "16:9",
        },
    },
    "seedance-2-image": {
        "endpoint": "bytedance/seedance-2.0/image-to-video",
        "kind": "image-to-video",
        "example": {
            "prompt": "A cinematic tracking shot",
            "resolution": "720p",
            "generate_audio": True,
            "duration": 5,
            "image_url": "https://example.com/first-frame.jpg",
        },
    },
    "seedance-2.5-text": {
        "endpoint": "bytedance/seedance-2.5/text-to-video",
        "kind": "text-to-video",
        "example": {
            "prompt": "A cinematic tracking shot along a sunlit coastal road",
            "resolution": "720p",
            "duration": 5,
            "aspect_ratio": "16:9",
        },
    },
}


def resolve_endpoint(value: str) -> str:
    return str(STARTERS.get(value, {}).get("endpoint", value))
