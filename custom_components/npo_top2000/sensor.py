"""Sensor platform for NPO Top 2000 integration."""
import logging
from datetime import datetime
from typing import Any, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_CURRENT_SONG,
    SENSOR_UPCOMING_SONGS,
    ATTR_POSITION,
    ATTR_ARTIST,
    ATTR_TITLE,
    ATTR_YEAR,
    ATTR_FUN_FACT_1,
    ATTR_FUN_FACT_2,
    ATTR_FUN_FACT_3,
    ATTR_COVER_ART_URL,
    ATTR_DETECTED_AT,
    ATTR_SONGS,
    ATTR_COUNT,
    ATTR_CURRENT_POSITION,
    CONF_UPCOMING_COUNT,
    DEFAULT_UPCOMING_COUNT,
)
from .coordinator import Top2000DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Top 2000 sensors from a config entry."""
    coordinator: Top2000DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    upcoming_count = entry.data.get(CONF_UPCOMING_COUNT, DEFAULT_UPCOMING_COUNT)

    sensors = [
        CurrentSongSensor(coordinator, entry),
        UpcomingSongsSensor(coordinator, entry, upcoming_count),
    ]

    async_add_entities(sensors)


class CurrentSongSensor(CoordinatorEntity, SensorEntity):
    """Sensor for the currently playing Top 2000 song."""

    def __init__(
        self,
        coordinator: Top2000DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "NPO Top 2000 Current Song"
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_CURRENT_SONG}"
        self._attr_icon = "mdi:music-note"

    @property
    def native_value(self) -> Optional[str]:
        """Return the state of the sensor."""
        if not self.coordinator.data or not self.coordinator.data.get("current_song"):
            return "unavailable"

        song = self.coordinator.data["current_song"]
        position = song.get("position", "?")
        artist = song.get("artist", "Unknown")
        title = song.get("title", "Unknown")

        return f"#{position}: {artist} - {title}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data or not self.coordinator.data.get("current_song"):
            return {}

        song = self.coordinator.data["current_song"]
        fun_facts = song.get("fun_facts", [])

        attrs = {
            ATTR_POSITION: song.get("position"),
            ATTR_ARTIST: song.get("artist"),
            ATTR_TITLE: song.get("title"),
            ATTR_YEAR: song.get("year"),
            ATTR_COVER_ART_URL: song.get("cover_art_url"),
            ATTR_DETECTED_AT: datetime.now().isoformat(),
        }

        # Add fun facts (up to 3)
        if len(fun_facts) > 0:
            attrs[ATTR_FUN_FACT_1] = fun_facts[0]
        if len(fun_facts) > 1:
            attrs[ATTR_FUN_FACT_2] = fun_facts[1]
        if len(fun_facts) > 2:
            attrs[ATTR_FUN_FACT_3] = fun_facts[2]

        # Add position history
        position_history = song.get("position_history", [])
        if position_history:
            attrs["position_history"] = position_history

            # Calculate trend (if we have previous year)
            if len(position_history) > 0:
                current_pos = song.get("position", 0)
                prev_year_data = position_history[0]  # Most recent previous year
                prev_pos = prev_year_data.get("position", current_pos)

                if prev_pos > current_pos:
                    attrs["position_trend"] = f"↑ {prev_pos - current_pos}"
                    attrs["position_trend_direction"] = "up"
                elif prev_pos < current_pos:
                    attrs["position_trend"] = f"↓ {current_pos - prev_pos}"
                    attrs["position_trend_direction"] = "down"
                else:
                    attrs["position_trend"] = "→ 0"
                    attrs["position_trend_direction"] = "same"

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.coordinator.data.get("current_song") is not None
        )


class UpcomingSongsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for upcoming Top 2000 songs."""

    def __init__(
        self,
        coordinator: Top2000DataUpdateCoordinator,
        entry: ConfigEntry,
        upcoming_count: int = DEFAULT_UPCOMING_COUNT,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "NPO Top 2000 Upcoming Songs"
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_UPCOMING_SONGS}"
        self._attr_icon = "mdi:playlist-music"
        self._upcoming_count = upcoming_count
        self._upcoming_songs: list[dict] = []

    @property
    def native_value(self) -> int:
        """Return the number of upcoming songs."""
        return len(self._upcoming_songs)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            ATTR_COUNT: len(self._upcoming_songs),
            ATTR_SONGS: self._upcoming_songs,
        }

        if self.coordinator.data and self.coordinator.data.get("current_song"):
            attrs[ATTR_CURRENT_POSITION] = self.coordinator.data["current_song"].get("position")

        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()

        # Only fetch upcoming songs when current song changes
        if self.coordinator.data and self.coordinator.data.get("song_changed", False):
            self.hass.async_create_task(self._async_update_upcoming())

    async def _async_update_upcoming(self) -> None:
        """Update upcoming songs list."""
        upcoming = await self.coordinator.async_get_upcoming_songs(self._upcoming_count)

        # Format upcoming songs for attributes
        self._upcoming_songs = []
        for song in upcoming:
            song_data = {
                "position": song.get("position"),
                "artist": song.get("artist"),
                "title": song.get("title"),
                "year": song.get("year"),
                "cover_art_url": song.get("cover_art_url"),
            }

            # Add position history for each song
            position_history = song.get("position_history", [])
            if position_history:
                song_data["position_history"] = position_history

                # Calculate trend
                if len(position_history) > 0:
                    current_pos = song.get("position", 0)
                    prev_pos = position_history[0].get("position", current_pos)

                    if prev_pos > current_pos:
                        song_data["position_trend"] = f"↑ {prev_pos - current_pos}"
                    elif prev_pos < current_pos:
                        song_data["position_trend"] = f"↓ {current_pos - prev_pos}"
                    else:
                        song_data["position_trend"] = "→ 0"

            self._upcoming_songs.append(song_data)

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
        )
