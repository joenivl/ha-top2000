"""MusicBrainz Cover Art Archive client."""
import asyncio
import logging
import musicbrainzngs
from datetime import datetime, timedelta
from typing import Optional

from .const import (
    MUSICBRAINZ_APP_NAME,
    MUSICBRAINZ_VERSION,
    MUSICBRAINZ_CONTACT,
    CACHE_DURATION_HOURS,
)

_LOGGER = logging.getLogger(__name__)


class CoverArtClient:
    """Client for fetching cover art from MusicBrainz Cover Art Archive."""

    def __init__(self):
        """Initialize MusicBrainz client."""
        # Configure musicbrainzngs
        musicbrainzngs.set_useragent(
            MUSICBRAINZ_APP_NAME,
            MUSICBRAINZ_VERSION,
            MUSICBRAINZ_CONTACT,
        )
        # Use Cover Art Archive hostname
        musicbrainzngs.set_caa_hostname("coverartarchive.org")

    async def get_cover_art(
        self,
        artist: str,
        title: str,
        cached_url: Optional[str] = None,
        cached_at: Optional[datetime] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Get cover art URL for a track.

        Returns tuple of (cover_art_url, musicbrainz_id) or (None, None) if not found.

        Args:
            artist: Artist name
            title: Track title
            cached_url: Previously cached URL (if any)
            cached_at: When the URL was cached (if any)

        Returns:
            Tuple of (cover_art_url, musicbrainz_release_id) or (None, None)
        """
        # Use cache if fresh (< 24 hours old)
        if cached_url and cached_at:
            cache_age = datetime.now() - cached_at
            if cache_age < timedelta(hours=CACHE_DURATION_HOURS):
                _LOGGER.debug("Using cached cover art for %s - %s", artist, title)
                return (cached_url, None)  # Don't return MB ID from cache

        _LOGGER.debug("Fetching cover art for %s - %s", artist, title)

        try:
            # Search MusicBrainz for the recording
            musicbrainz_id, cover_url = await self._search_musicbrainz(artist, title)

            if cover_url:
                _LOGGER.info("Found cover art for %s - %s", artist, title)
                return (cover_url, musicbrainz_id)
            else:
                _LOGGER.warning("No cover art found for %s - %s", artist, title)
                return (None, musicbrainz_id)

        except Exception as err:
            _LOGGER.error("Failed to fetch cover art for %s - %s: %s", artist, title, err)
            return (None, None)

    async def _search_musicbrainz(
        self,
        artist: str,
        title: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Search MusicBrainz for recording and fetch cover art.

        Returns tuple of (musicbrainz_release_id, cover_art_url).
        """
        try:
            # Search for releases (not recordings) as they have cover art
            query = f'artist:"{artist}" AND recording:"{title}"'
            _LOGGER.debug("MusicBrainz query: %s", query)

            # Run blocking MusicBrainz call in separate thread
            result = await asyncio.to_thread(
                musicbrainzngs.search_releases,
                query=query,
                limit=5
            )

            if not result or "release-list" not in result:
                _LOGGER.debug("No releases found in MusicBrainz")
                return (None, None)

            releases = result["release-list"]
            if not releases:
                _LOGGER.debug("Empty release list from MusicBrainz")
                return (None, None)

            # Try to get cover art for the first few releases
            for release in releases[:3]:  # Try top 3 matches
                release_id = release.get("id")
                if not release_id:
                    continue

                _LOGGER.debug("Trying release ID: %s", release_id)

                try:
                    # Get cover art images for this release (run in thread)
                    images = await asyncio.to_thread(
                        musicbrainzngs.get_image_list,
                        release_id
                    )

                    if images and "images" in images and images["images"]:
                        # Prefer 'front' cover, fallback to first image
                        for img in images["images"]:
                            if img.get("front") and "thumbnails" in img:
                                # Use 500px thumbnail
                                cover_url = img["thumbnails"].get("500") or img["thumbnails"].get("large")
                                if cover_url:
                                    return (release_id, cover_url)

                        # No front cover found, use first available thumbnail
                        first_img = images["images"][0]
                        if "thumbnails" in first_img:
                            cover_url = first_img["thumbnails"].get("500") or first_img["thumbnails"].get("large")
                            if cover_url:
                                return (release_id, cover_url)

                except musicbrainzngs.musicbrainz.ResponseError as err:
                    # 404 means no cover art for this release, try next
                    if "404" in str(err):
                        _LOGGER.debug("No cover art for release %s", release_id)
                        continue
                    else:
                        raise

            _LOGGER.debug("No cover art found in any of the releases")
            return (None, None)

        except musicbrainzngs.musicbrainz.NetworkError as err:
            _LOGGER.error("MusicBrainz network error: %s", err)
            return (None, None)
        except musicbrainzngs.musicbrainz.ResponseError as err:
            _LOGGER.error("MusicBrainz response error: %s", err)
            return (None, None)
        except Exception as err:
            _LOGGER.error("Unexpected error searching MusicBrainz: %s", err)
            return (None, None)
