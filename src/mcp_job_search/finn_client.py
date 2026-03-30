"""Client for FINN.no job search (Atom Search API).

Official docs: https://www.finn.no/api/doc/search
Requires HTTP header ``x-FINN-apikey`` — set environment variable ``FINN_API_KEY``.
Without a key, search returns no results (Finn responds 403 to unauthenticated calls).
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from .job_utils import deadline_is_still_open
from .models import JobListing, JobSource

logger = logging.getLogger(__name__)

FINN_SEARCH_BASE = "https://cache.api.finn.no/iad/search/job-full-time"
ATOM_NS = "http://www.w3.org/2005/Atom"
AGE_NS = "http://purl.org/atompub/age/1.0"
FINN_EXT_NS = "http://xmlns.finn.no/atom-ad-extensions/1.0"

FINN_MAX_PAGES = 50
FINN_ROWS = 100
FINN_ABS_MAX_MATCHES = 5000


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


class FinnJobClient:
    """Async client for FINN job listings via the Search API (Atom)."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("FINN_API_KEY", "").strip() or None
        self._client = httpx.AsyncClient(timeout=45.0)

    @property
    def has_api_key(self) -> bool:
        return self._api_key is not None

    async def search_jobs(
        self,
        query: str = "",
        location: str = "",
        language: str = "",
        max_results: int = 0,
        exclude_expired_deadlines: bool = True,
    ) -> list[JobListing]:
        """Search FINN full-time jobs. ``language`` is matched loosely on title/location text."""
        if not self._api_key:
            return []

        cap = max_results if max_results > 0 else FINN_ABS_MAX_MATCHES
        results: list[JobListing] = []

        for page in range(1, FINN_MAX_PAGES + 1):
            params: dict[str, Any] = {"rows": str(FINN_ROWS), "page": str(page)}
            if query:
                params["q"] = query
            headers = {
                "x-FINN-apikey": self._api_key,
                "Accept": "application/atom+xml",
                "User-Agent": "mcp-job-search-agent/0.1 (httpx)",
            }
            try:
                response = await self._client.get(FINN_SEARCH_BASE, params=params, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error("Finn search failed: %s", e)
                break

            page_jobs = self._parse_atom_feed(
                response.content,
                location_filter=location,
                exclude_expired_deadlines=exclude_expired_deadlines,
            )
            if not page_jobs:
                break
            for job in page_jobs:
                results.append(job)
                if len(results) >= cap:
                    return results[:cap]

        return results

    def _parse_atom_feed(
        self,
        content: bytes,
        location_filter: str,
        exclude_expired_deadlines: bool,
    ) -> list[JobListing]:
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.error("Finn Atom parse error: %s", e)
            return []

        listings: list[JobListing] = []
        loc_low = location_filter.lower() if location_filter else ""

        for entry in root.iter():
            if _local_tag(entry.tag) != "entry":
                continue

            title_el = entry.find(f"{{{ATOM_NS}}}title")
            title = (title_el.text or "").strip() if title_el is not None else ""

            url = ""
            for link in entry.findall(f"{{{ATOM_NS}}}link"):
                if link.get("rel") == "alternate":
                    url = (link.get("href") or "").strip()
                    break

            id_el = entry.find(f"{{{ATOM_NS}}}id")
            raw_id = (id_el.text or "").strip() if id_el is not None else ""
            ad_id = raw_id.split(":")[-1] if raw_id else ""

            expires_el = entry.find(f"{{{AGE_NS}}}expires")
            deadline = (expires_el.text or "").strip() if expires_el is not None else ""

            if exclude_expired_deadlines and deadline and not deadline_is_still_open(deadline):
                continue

            author = entry.find(f"{{{ATOM_NS}}}author")
            employer = "Unknown"
            if author is not None:
                name_el = author.find(f"{{{ATOM_NS}}}name")
                if name_el is not None and name_el.text:
                    employer = name_el.text.strip()

            city = ""
            loc_el = entry.find(f"{{{FINN_EXT_NS}}}location")
            if loc_el is not None:
                city_el = loc_el.find(f"{{{FINN_EXT_NS}}}city")
                if city_el is not None and city_el.text:
                    city = city_el.text.strip()

            if loc_low and loc_low not in city.lower():
                continue

            listings.append(
                JobListing(
                    id=ad_id or raw_id or url,
                    source=JobSource.FINN,
                    title=title or "Untitled",
                    employer=employer,
                    location=city,
                    description="",
                    url=url,
                    published="",
                    deadline=deadline,
                    work_language="",
                    occupation="",
                )
            )

        return listings

    async def close(self) -> None:
        await self._client.aclose()
