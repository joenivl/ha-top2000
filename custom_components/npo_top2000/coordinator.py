"""DataUpdateCoordinator for NPO Top 2000 integration."""
import logging
import json
from datetime import timedelta
from typing import Optional

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    DEFAULT_UPDATE_INTERVAL,
)
from .database import DatabaseManager
from .npo_client import NPOClient
from .coverart import CoverArtClient

_LOGGER = logging.getLogger(__name__)


class Top2000DataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Top 2000 data from NPO."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        db_manager: DatabaseManager,
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
    ):
        """Initialize coordinator."""
        self.db_manager = db_manager
        self.npo_client = NPOClient(session)
        self.coverart_client = CoverArtClient()

        # Track last known song to detect changes
        self._last_song_id: Optional[int] = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self) -> dict:
        """
        Fetch data from NPO Radio 2 and match against database.

        Returns dict with:
        - current_song: Song data dict or None
        - song_changed: Boolean indicating if song changed since last update
        """
        try:
            # Step 1: Fetch current NPO metadata
            _LOGGER.debug("Fetching NPO Radio 2 metadata")
            npo_metadata = await self.npo_client.get_current_metadata()

            if not npo_metadata:
                _LOGGER.warning("No metadata available from NPO")
                # Return last known state or unavailable
                return {
                    "current_song": None,
                    "song_changed": False,
                    "error": "No metadata available",
                }

            artist = npo_metadata.get("artist")
            title = npo_metadata.get("title")

            _LOGGER.info("Current NPO track: %s - %s", artist, title)

            # Step 2: Match against Top 2000 database
            song_match = await self.db_manager.match_song(artist, title)

            if not song_match:
                _LOGGER.warning("No match found in Top 2000 database for %s - %s", artist, title)
                return {
                    "current_song": None,
                    "song_changed": False,
                    "error": f"Not in Top 2000: {artist} - {title}",
                    "raw_metadata": npo_metadata,
                }

            song_id = song_match["id"]
            song_changed = song_id != self._last_song_id

            if song_changed:
                _LOGGER.info(
                    "Song changed: #%d %s - %s",
                    song_match["position"],
                    song_match["artist"],
                    song_match["title"],
                )
                self._last_song_id = song_id

                # Step 3: Fetch cover art (only when song changes)
                # Pass NPO's cover art URL if available
                npo_cover_url = npo_metadata.get("cover_art_url")
                await self._fetch_and_cache_cover_art(song_match, npo_cover_url)

                # Step 4: Update playlist state in database
                await self.db_manager.update_playlist_state(
                    position=song_match["position"],
                    song_id=song_id,
                    npo_metadata=json.dumps(npo_metadata),
                )

                # Step 5: Check notification rules and send notifications
                await self._check_and_send_notifications(song_match, is_current=True)

                # Step 6: Check upcoming songs for notifications (only when song changes)
                await self.async_check_upcoming_notifications()

            # Return coordinated data
            return {
                "current_song": song_match,
                "song_changed": song_changed,
                "npo_metadata": npo_metadata,
            }

        except Exception as err:
            _LOGGER.error("Error updating data: %s", err)
            raise UpdateFailed(f"Error communicating with NPO Radio 2: {err}")

    async def _fetch_and_cache_cover_art(self, song_data: dict, npo_cover_url: Optional[str] = None) -> None:
        """Fetch and cache cover art for a song."""
        song_id = song_data["id"]

        # If NPO provided a cover art URL, use it directly
        if npo_cover_url:
            _LOGGER.debug("Using cover art from NPO for song %d", song_id)
            await self.db_manager.update_cover_art(
                song_id=song_id,
                cover_art_url=npo_cover_url,
                musicbrainz_id=None,
            )
            song_data["cover_art_url"] = npo_cover_url
            return

        # Check if already cached from previous run
        if await self.db_manager.is_cover_art_cached(song_id):
            _LOGGER.debug("Cover art already cached for song %d", song_id)
            return

        # Fallback: Fetch cover art from MusicBrainz
        cover_url, mb_id = await self.coverart_client.get_cover_art(
            artist=song_data["artist"],
            title=song_data["title"],
            cached_url=song_data.get("cover_art_url"),
            cached_at=song_data.get("cover_art_cached_at"),
        )

        # Update database
        if cover_url:
            await self.db_manager.update_cover_art(
                song_id=song_id,
                cover_art_url=cover_url,
                musicbrainz_id=mb_id,
            )
            song_data["cover_art_url"] = cover_url
            _LOGGER.info("Updated cover art from MusicBrainz for song %d", song_id)
        else:
            _LOGGER.warning("No cover art found for song %d", song_id)

    async def async_get_upcoming_songs(self, count: int = 10) -> list[dict]:
        """Get upcoming songs based on current position."""
        if not self.data or not self.data.get("current_song"):
            return []

        current_position = self.data["current_song"]["position"]
        upcoming = await self.db_manager.get_upcoming_songs(current_position, count)

        return upcoming

    async def _check_and_send_notifications(
        self, song_data: dict, is_current: bool = True
    ) -> None:
        """
        Check notification rules and send notifications.

        Args:
            song_data: Song data dictionary
            is_current: True if this is the current song, False if upcoming
        """
        # Get notification settings
        settings = await self.db_manager.get_notification_settings()

        # Check if we should notify for this type (current or upcoming)
        if is_current and not settings.get("notify_current_song", True):
            return
        if not is_current and not settings.get("notify_upcoming_song", False):
            return

        # Check if song matches any notification rules
        if not await self._matches_notification_rules(song_data):
            return

        # Send notifications to all configured targets
        await self._send_notification(song_data, settings, is_current)

    async def _matches_notification_rules(self, song_data: dict) -> bool:
        """
        Check if song matches any notification rules.

        Returns True if song matches at least one rule.
        """
        rules = await self.db_manager.get_notification_rules(enabled_only=True)

        if not rules:
            return False

        artist = song_data.get("artist", "").lower()
        title = song_data.get("title", "").lower()

        for rule in rules:
            rule_type = rule["rule_type"]
            pattern = rule["match_pattern"].lower()

            if rule_type == "artist" and pattern in artist:
                _LOGGER.info("Notification rule matched: artist '%s'", pattern)
                return True
            elif rule_type == "title" and pattern in title:
                _LOGGER.info("Notification rule matched: title '%s'", pattern)
                return True
            elif rule_type == "position_range":
                # Position range logic (to be implemented)
                pass

        return False

    async def _send_notification(
        self, song_data: dict, settings: dict, is_current: bool = True
    ) -> None:
        """Send notification to all configured targets."""
        position = song_data.get("position", "?")
        artist = song_data.get("artist", "Unknown")
        title = song_data.get("title", "Unknown")
        year = song_data.get("year", "")
        fun_facts = song_data.get("fun_facts", [])

        # Create notification message
        if is_current:
            message = f"Nu op Radio 2:\n#{position}: {artist} - {title}"
        else:
            message = f"Binnenkort op Radio 2:\n#{position}: {artist} - {title}"

        if year:
            message += f" ({year})"

        # Add fun fact if available
        if fun_facts:
            message += f"\n\n💡 {fun_facts[0]}"

        # Get notification targets
        targets = settings.get("notification_targets", ["persistent_notification"])

        # Send to each target
        for target in targets:
            try:
                if target == "persistent_notification":
                    # Send persistent notification
                    await self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "title": "NPO Radio 2 Top 2000",
                            "message": message,
                            "notification_id": f"top2000_{song_data.get('id')}_{is_current}",
                        },
                    )
                else:
                    # Send to notify service (e.g., notify.mobile_app_iphone)
                    # Extract domain and service
                    if "." in target:
                        domain, service = target.split(".", 1)
                    else:
                        domain = "notify"
                        service = target

                    await self.hass.services.async_call(
                        domain,
                        service,
                        {
                            "title": "NPO Radio 2 Top 2000",
                            "message": message,
                            "data": {
                                "image": song_data.get("cover_art_url"),
                            },
                        },
                    )

                _LOGGER.info(
                    "Sent notification to %s for #%d: %s - %s",
                    target,
                    position,
                    artist,
                    title,
                )
            except Exception as err:
                _LOGGER.error("Failed to send notification to %s: %s", target, err)

    async def async_check_upcoming_notifications(self) -> None:
        """Check if any upcoming songs match notification rules."""
        if not self.data or not self.data.get("current_song"):
            return

        # Get notification settings
        settings = await self.db_manager.get_notification_settings()

        if not settings.get("notify_upcoming_song", False):
            return

        # Get positions to check
        positions_to_check = settings.get("upcoming_notify_positions", [1, 2, 3])
        current_position = self.data["current_song"]["position"]

        # Get upcoming songs (Top 2000 counts DOWN from 2000 to 1)
        for offset in positions_to_check:
            upcoming_position = current_position - offset
            if upcoming_position < 1:
                continue

            # Get song at this position
            upcoming_song = await self.db_manager.get_song_by_position(upcoming_position)
            if upcoming_song and await self._matches_notification_rules(upcoming_song):
                await self._send_notification(upcoming_song, settings, is_current=False)
