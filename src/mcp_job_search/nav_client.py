"""Client for the NAV Arbeidsplassen job feed API.

API docs: https://navikt.github.io/pam-stilling-feed/
The NAV job feed provides access to publicly advertised job vacancies in Norway.
Authentication is via a signed JWT token (a public token is available for experiments).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .job_utils import deadline_is_still_open, extract_jwt_from_text
from .models import JobListing, JobSource

logger = logging.getLogger(__name__)

# Safety caps (feed is paginated; avoid unbounded memory)
NAV_MAX_FEED_PAGES = 50
NAV_PAGE_SIZE = 100
NAV_ABS_MAX_MATCHES = 5000

NAV_FEED_BASE_URL = "https://pam-stilling-feed.nav.no"
NAV_PUBLIC_TOKEN_URL = f"{NAV_FEED_BASE_URL}/api/publicToken"
NAV_FEED_URL = f"{NAV_FEED_BASE_URL}/api/v1/feed"
NAV_AD_DETAIL_URL = f"{NAV_FEED_BASE_URL}/api/v1/ads"


class NAVJobClient:
    """Async client for fetching jobs from NAV's Arbeidsplassen API."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token
        self._client = httpx.AsyncClient(timeout=30.0)

    async def _get_public_token(self) -> str:
        """Fetch the rotating public token for experiments."""
        response = await self._client.get(NAV_PUBLIC_TOKEN_URL)
        response.raise_for_status()
        return extract_jwt_from_text(response.text)

    async def _get_token(self) -> str:
        """Get the authentication token (cached or fetched)."""
        if self._token is None:
            self._token = await self._get_public_token()
        return self._token

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    async def fetch_feed(self, size: int = 100) -> list[dict[str, Any]]:
        """Fetch the latest single page from the job feed."""
        items = await self.fetch_feed_pages(max_pages=1, page_size=size)
        return items

    async def fetch_feed_pages(
        self,
        max_pages: int = NAV_MAX_FEED_PAGES,
        page_size: int = NAV_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        """Fetch multiple feed pages using `next_url` until exhausted or max_pages."""
        headers = await self._auth_headers()
        url: str | None = NAV_FEED_URL
        params: dict[str, str] | None = {"size": str(page_size)}
        all_items: list[dict[str, Any]] = []

        for _ in range(max_pages):
            if not url:
                break
            try:
                response = await self._client.get(url, headers=headers, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error("NAV feed request failed: %s", e)
                if e.response.status_code == 401:
                    self._token = None
                    headers = await self._auth_headers()
                    response = await self._client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                else:
                    raise
            data = response.json()
            all_items.extend(data.get("items", []))
            next_url = data.get("next_url") or data.get("nextUrl")
            if not next_url:
                break
            if not str(next_url).startswith("http"):
                next_url = f"{NAV_FEED_BASE_URL}{next_url}"
            url = str(next_url)
            params = None

        return all_items

    async def get_ad_details(self, uuid: str) -> dict[str, Any] | None:
        """Fetch full details for a specific job ad.

        Args:
            uuid: The ad UUID from the feed.

        Returns:
            Full ad details dict, or None if not found.
        """
        headers = await self._auth_headers()
        url = f"{NAV_AD_DETAIL_URL}/{uuid}"

        try:
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def search_jobs(
        self,
        query: str = "",
        location: str = "",
        language: str = "",
        max_results: int = 0,
        exclude_expired_deadlines: bool = True,
    ) -> list[JobListing]:
        """Search for jobs by fetching the feed and filtering locally.

        The NAV feed API is a chronological feed (not a search API), so we
        fetch paginated entries and filter client-side.

        Args:
            query: Keywords to search for in title/description.
            location: Filter by location name.
            language: Filter by working language.
            max_results: Maximum matches to return (0 = no cap up to safety limit).
            exclude_expired_deadlines: Drop ads whose application deadline is in the past.

        Returns:
            List of matching JobListing objects.
        """
        raw_items = await self.fetch_feed_pages()
        results: list[JobListing] = []
        query_lower = query.lower()

        cap = max_results if max_results > 0 else NAV_ABS_MAX_MATCHES

        for item in raw_items:
            feed_entry = item.get("_feed_entry", {})

            # Skip inactive ads
            if feed_entry.get("status") != "ACTIVE":
                continue

            # Extract fields from the feed item
            title = item.get("title", "")
            employer_name = ""
            employer_info = item.get("businessName", "") or item.get("employer", "")
            if isinstance(employer_info, dict):
                employer_name = employer_info.get("name", "")
            else:
                employer_name = str(employer_info)

            item_location = item.get("municipal", "") or item.get("county", "")
            description = item.get("description", "") or ""
            work_lang = item.get("workLanguage", "") or ""
            occupation = item.get("occupationList", "")
            if isinstance(occupation, list) and occupation:
                occupation = ", ".join(
                    o.get("level2", "") if isinstance(o, dict) else str(o)
                    for o in occupation
                )
            else:
                occupation = str(occupation) if occupation else ""

            ad_url = item.get("link", "") or ""
            published = item.get("published", "") or ""
            deadline = item.get("applicationDue", "") or ""
            ad_uuid = feed_entry.get("id", item.get("uuid", ""))

            # Apply filters
            if exclude_expired_deadlines and deadline and not deadline_is_still_open(deadline):
                continue
            searchable = f"{title} {employer_name} {description} {occupation}".lower()
            if query_lower and query_lower not in searchable:
                continue
            if location and location.lower() not in item_location.lower():
                continue
            if language and language.lower() not in work_lang.lower():
                continue

            results.append(
                JobListing(
                    id=str(ad_uuid),
                    source=JobSource.NAV,
                    title=title,
                    employer=employer_name,
                    location=item_location,
                    description=description[:500],  # Truncate for readability
                    url=ad_url,
                    published=published,
                    deadline=deadline,
                    work_language=work_lang,
                    occupation=occupation,
                )
            )

            if len(results) >= cap:
                break

        return results

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
