"""NPO Radio 2 metadata client with fallback strategies."""
import logging
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Optional

from .const import (
    NPO_LIVE_URL,
    NPO_STREAM_URL,
    FALLBACK_URL,
    HTTP_TIMEOUT_CONNECT,
    HTTP_TIMEOUT_READ,
    HTTP_USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class NPOClient:
    """Client for fetching NPO Radio 2 metadata with fallback strategies."""

    def __init__(self, session: aiohttp.ClientSession):
        """Initialize NPO client."""
        self.session = session
        self._last_fetch: Optional[datetime] = None
        self._cached_metadata: Optional[dict] = None
        self._cache_duration = timedelta(seconds=30)

    async def get_current_metadata(self) -> Optional[dict]:
        """
        Fetch current NPO Radio 2 metadata with 3-tier fallback.

        Returns dict with 'artist' and 'title' keys, or None if all strategies fail.
        """
        # Check cache first (30 second cache)
        if self._cached_metadata and self._last_fetch:
            if datetime.now() - self._last_fetch < self._cache_duration:
                _LOGGER.debug("Returning cached metadata")
                return self._cached_metadata

        # Strategy 1: Try NPO website first
        try:
            metadata = await self._scrape_npo_website()
            if metadata:
                self._cache_metadata(metadata)
                return metadata
        except Exception as err:
            _LOGGER.warning("NPO website scraping failed: %s", err)

        # Strategy 2: Try Icecast metadata
        try:
            metadata = await self._fetch_icecast_metadata()
            if metadata:
                self._cache_metadata(metadata)
                return metadata
        except Exception as err:
            _LOGGER.warning("Icecast metadata failed: %s", err)

        # Strategy 3: Fallback to onlineradiobox
        try:
            metadata = await self._scrape_onlineradiobox()
            if metadata:
                self._cache_metadata(metadata)
                return metadata
        except Exception as err:
            _LOGGER.error("All metadata sources failed: %s", err)

        return None

    def _cache_metadata(self, metadata: dict) -> None:
        """Cache metadata."""
        self._cached_metadata = metadata
        self._last_fetch = datetime.now()
        _LOGGER.debug("Cached metadata: %s - %s", metadata.get("artist"), metadata.get("title"))

    async def _scrape_npo_website(self) -> Optional[dict]:
        """
        Primary strategy: Scrape NPO Radio 2 homepage.

        The NPO homepage contains Next.js data with trackPlaysList showing recently played tracks.
        """
        _LOGGER.debug("Attempting to scrape NPO homepage")

        timeout = aiohttp.ClientTimeout(
            total=None,
            connect=HTTP_TIMEOUT_CONNECT,
            sock_read=HTTP_TIMEOUT_READ,
        )

        headers = {"User-Agent": HTTP_USER_AGENT}

        # Use homepage instead of /live
        npo_homepage = "https://www.nporadio2.nl/"

        async with self.session.get(npo_homepage, timeout=timeout, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            # Find Next.js data
            next_data = soup.find("script", {"id": "__NEXT_DATA__"})
            if not next_data:
                _LOGGER.warning("No __NEXT_DATA__ found in NPO homepage")
                return None

            try:
                import json
                data = json.loads(next_data.string)

                # Navigate to trackPlaysList
                props = data.get("props", {})
                page_props = props.get("pageProps", {})
                track_plays_list = page_props.get("trackPlaysList", {})
                tracks_plays = track_plays_list.get("tracksPlays", [])

                if not tracks_plays:
                    _LOGGER.warning("No tracks found in trackPlaysList")
                    return None

                # First track is the most recent (currently playing or just played)
                current_track = tracks_plays[0]

                artist = current_track.get("artist", "Unknown")
                title = current_track.get("name", "Unknown")

                # NPO provides cover art URLs - extract if available
                image_url = None
                if "image" in current_track:
                    image_url = current_track["image"]
                elif "imageUrl" in current_track:
                    image_url = current_track["imageUrl"]

                _LOGGER.debug("Found track from NPO homepage: %s - %s", artist, title)
                if image_url:
                    _LOGGER.debug("NPO cover art URL: %s", image_url)

                return {
                    "artist": artist,
                    "title": title,
                    "cover_art_url": image_url,  # Include NPO's cover art
                }

            except Exception as e:
                _LOGGER.error("Failed to parse __NEXT_DATA__: %s", e)
                return None

    async def _fetch_icecast_metadata(self) -> Optional[dict]:
        """
        Secondary strategy: Fetch Icecast stream metadata.

        NPO streams use Icecast which includes metadata in HTTP headers.
        """
        _LOGGER.debug("Attempting to fetch Icecast metadata")

        timeout = aiohttp.ClientTimeout(
            total=None,
            connect=HTTP_TIMEOUT_CONNECT,
            sock_read=5,  # Short read timeout for stream
        )

        headers = {
            "User-Agent": HTTP_USER_AGENT,
            "Icy-MetaData": "1",  # Request metadata
        }

        async with self.session.get(NPO_STREAM_URL, timeout=timeout, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")

            # Check for ICY metadata in headers
            icy_meta = resp.headers.get("icy-name") or resp.headers.get("ice-audio-info")

            if icy_meta:
                # Parse ICY metadata format: "Artist - Title"
                if " - " in icy_meta:
                    parts = icy_meta.split(" - ", 1)
                    return {
                        "artist": parts[0].strip(),
                        "title": parts[1].strip(),
                    }

            _LOGGER.warning("No Icecast metadata found in stream headers")
            return None

    async def _scrape_onlineradiobox(self) -> Optional[dict]:
        """
        Tertiary fallback: Scrape onlineradiobox.com.

        This site tracks what's playing on many radio stations.
        """
        _LOGGER.debug("Attempting to scrape onlineradiobox.com")

        timeout = aiohttp.ClientTimeout(
            total=None,
            connect=HTTP_TIMEOUT_CONNECT,
            sock_read=HTTP_TIMEOUT_READ,
        )

        headers = {"User-Agent": HTTP_USER_AGENT}

        async with self.session.get(FALLBACK_URL, timeout=timeout, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            # Look for track info in common structures
            # onlineradiobox typically uses specific classes
            track_info = soup.find(class_=["track_history_item", "track-title"])

            if track_info:
                # Try to find artist and title elements
                artist_elem = track_info.find(class_=["track-artist", "artist"])
                title_elem = track_info.find(class_=["track-name", "title"])

                if artist_elem and title_elem:
                    return {
                        "artist": artist_elem.get_text(strip=True),
                        "title": title_elem.get_text(strip=True),
                    }

                # Sometimes it's just one element with "Artist - Title"
                text = track_info.get_text(strip=True)
                if " - " in text:
                    parts = text.split(" - ", 1)
                    return {
                        "artist": parts[0].strip(),
                        "title": parts[1].strip(),
                    }

            _LOGGER.warning("Could not find track metadata in onlineradiobox")
            return None
