"""Data importer for Top 2000 from GitHub repository."""
import re
import logging
import aiohttp
from pathlib import Path
from typing import Optional

from .database import DatabaseManager

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://raw.githubusercontent.com/Top2000app/data/main/sql"

# Edition files - map year to SQL file for position data
EDITION_FILES = {
    2025: "0065-EditionOf2025.sql",
    2024: "0063-EditionOf2024.sql",
    2023: "0059-EditionOf2023.sql",
    2022: "0053-EditionOf2022.sql",
    2021: "0050-EditionOf2021.sql",
    2020: "0046-EditionOf2020.sql",
    2019: "0044-EditionOf2019.sql",
    2018: "0041-EditionOf2018.sql",
    # Add more years as needed
}

# Track files - all year files that contain Track INSERT statements
# Based on the GitHub repository structure
TRACK_FILES = [
    "0002-1999.sql",
    "0004-2000.sql",
    "0006-2001.sql",
    "0008-2002.sql",
    "0010-2003.sql",
    "0012-2004.sql",
    "0014-2005.sql",
    "0016-2006.sql",
    "0018-2007.sql",
    "0020-2008.sql",
    "0022-2009.sql",
    "0024-2010.sql",
    "0026-2011.sql",
    "0028-2012.sql",
    "0030-2013.sql",
    "0032-2014.sql",
    "0034-2015.sql",
    "0036-2016.sql",
    "0038-2017.sql",
    "0040-2018.sql",
    "0043-2019.sql",
    "0045-2020.sql",
    "0048-FixListings.sql",  # Contains 1 new track
    "0049-2021.sql",
    "0051-AviciiHeavenFix.sql",  # Contains 1 new track
    "0052-2022.sql",
    "0055-FixingLists.sql",  # Contains 3 new tracks
    "0056-2023.sql",
    "0058-2023_Full.sql",  # Full 2023 dataset
    "0062-2024.sql",
    "0064-2025.sql",
    "0066-RunLikeHell.sql",  # Contains 1 new track
]


class Top2000DataImporter:
    """Import Top 2000 data from GitHub SQL files."""

    def __init__(self, db_manager: DatabaseManager, import_years: list[int] | None = None):
        """Initialize importer.

        Args:
            db_manager: Database manager instance
            import_years: List of years to import position history for (default: [2023, 2024, 2025])
        """
        self.db_manager = db_manager
        self.tracks = {}  # track_id -> {artist, title, year}
        self.import_years = import_years or [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]  # Default: all available years

    async def import_data(self) -> bool:
        """
        Download and import Top 2000 data from GitHub.

        Returns True if successful, False otherwise.
        """
        try:
            # Check if database already has data
            if await self.db_manager.is_populated():
                _LOGGER.info("Database already populated, skipping import")
                return True

            _LOGGER.info("Starting Top 2000 data import from GitHub (years: %s)", self.import_years)

            # Step 1: Download and parse track data
            await self._import_tracks()

            # Step 2: Download and parse edition/listing data with positions
            # Import from the most recent year first (creates the songs table entries)
            sorted_years = sorted(self.import_years, reverse=True)
            first_year = sorted_years[0]

            # Import current year positions (creates songs)
            await self._import_listings(first_year, create_songs=True)

            # Import historical positions (only position_history)
            for year in sorted_years[1:]:
                await self._import_listings(year, create_songs=False)

            _LOGGER.info("Top 2000 data import completed successfully")
            return True

        except Exception as err:
            _LOGGER.error("Failed to import Top 2000 data: %s", err)
            return False

    async def _download_file(self, filename: str) -> str:
        """Download SQL file from GitHub."""
        url = f"{BASE_URL}/{filename}"
        _LOGGER.debug("Downloading %s", url)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download {filename}: HTTP {response.status}")
                return await response.text()

    async def _import_tracks(self) -> None:
        """Import track data (artist, title, year) from all SQL files."""
        _LOGGER.info("Importing track data from all historical SQL files")

        # Download and parse all track files
        for filename in TRACK_FILES:
            # Try to download the file
            try:
                _LOGGER.debug("Attempting to download %s", filename)
                sql_content = await self._download_file(filename)
                _LOGGER.debug("Downloaded %s (%d bytes)", filename, len(sql_content))
            except Exception as err:
                _LOGGER.warning("Failed to download file %s: %s", filename, err)
                continue

            # Parse INSERT statements for Track table
            # Multiple formats:
            # Format 1: (4975,'Lichtje Branden','Suzan & Freek',2021),
            # Format 2: , (1,'(Everything I Do) I Do It For You','Bryan Adams',1991)
            # Format 3: (4518, 'Soldier On','Di-rect',2020),  [with space after ID]
            # Pattern needs to handle all formats with optional spaces
            pattern = r"[,\s]*\((\d+)\s*,\s*'([^']+(?:''[^']+)*?)'\s*,\s*'([^']+(?:''[^']+)*?)'\s*,\s*(\d+)\)"

            matches = re.findall(pattern, sql_content, re.MULTILINE | re.DOTALL)

            if matches:
                _LOGGER.debug("Found %d tracks in %s", len(matches), filename)

                for match in matches:
                    track_id = int(match[0])
                    title = match[1].replace("''", "'")  # Unescape single quotes
                    artist = match[2].replace("''", "'")
                    year = int(match[3])

                    # Only add if not already present (newer files take precedence)
                    if track_id not in self.tracks:
                        self.tracks[track_id] = {
                            "artist": artist,
                            "title": title,
                            "year": year,
                        }

        _LOGGER.info("Parsed %d total tracks from all files", len(self.tracks))

    async def _import_listings(self, year: int, create_songs: bool = True) -> None:
        """Import listing data (positions) for a specific year.

        Args:
            year: Year to import (e.g., 2025)
            create_songs: If True, create song entries. If False, only add position_history.
        """
        edition_file = EDITION_FILES.get(year)
        if not edition_file:
            _LOGGER.warning("No edition file configured for year %d, skipping", year)
            return

        _LOGGER.info("Importing %s positions (year %d, create_songs=%s)",
                     "current" if create_songs else "historical", year, create_songs)

        try:
            sql_content = await self._download_file(edition_file)
        except Exception as err:
            _LOGGER.error("Failed to download edition file for year %d: %s", year, err)
            return

        # Parse INSERT statements for Listing table
        # Example: (397,2025,1,'2025-12-31T22:00:00') or (397, 2025, 1, '2025-12-31T22:00:00')
        # Handle both formats with and without spaces after commas
        pattern = r"\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'[^']+'\)"

        matches = re.findall(pattern, sql_content)

        _LOGGER.debug("Found %d listings for year %d", len(matches), year)

        imported_count = 0
        # Keep track of song_id mapping (track_id -> song_id)
        track_to_song_id = {}

        for match in matches:
            track_id = int(match[0])
            edition = int(match[1])
            position = int(match[2])

            # Get track data
            track = self.tracks.get(track_id)
            if not track:
                _LOGGER.warning("Track ID %d not found, skipping position %d", track_id, position)
                continue

            if create_songs:
                # Insert song into database
                song_id = await self.db_manager.insert_song(
                    position=position,
                    artist=track["artist"],
                    title=track["title"],
                    year=track["year"],
                )
                track_to_song_id[track_id] = song_id

                # Also add position history for this year
                await self.db_manager.add_position_history(
                    song_id=song_id,
                    year=year,
                    position=position,
                )
            else:
                # Historical data: find existing song by artist/title and add position_history
                song = await self.db_manager.get_song_by_artist_title(
                    artist=track["artist"],
                    title=track["title"],
                )

                if song:
                    await self.db_manager.add_position_history(
                        song_id=song["id"],
                        year=year,
                        position=position,
                    )
                else:
                    _LOGGER.debug("Song not found for track %d (%s - %s), skipping historical position",
                                  track_id, track["artist"], track["title"])
                    continue

            imported_count += 1

            if imported_count % 100 == 0:
                _LOGGER.debug("Imported %d/%d positions for year %d", imported_count, len(matches), year)

        _LOGGER.info("Imported %d positions for year %d", imported_count, year)


async def import_top2000_data(db_manager: DatabaseManager) -> bool:
    """
    Import Top 2000 data into database.

    Convenience function for importing data.
    """
    importer = Top2000DataImporter(db_manager)
    return await importer.import_data()
