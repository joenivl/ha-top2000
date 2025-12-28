"""Database manager for NPO Radio 2 Top 2000 integration."""
import aiosqlite
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from rapidfuzz import fuzz

from .const import (
    DB_NAME,
    CACHE_DURATION_HOURS,
    FUZZY_MATCH_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)

# SQL Schema
SCHEMA_SQL = """
-- Songs table
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position INTEGER NOT NULL UNIQUE,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    year INTEGER,
    musicbrainz_id TEXT,
    cover_art_url TEXT,
    cover_art_cached_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_position ON songs(position);
CREATE INDEX IF NOT EXISTS idx_artist_title ON songs(artist, title);

-- Position history table (track position changes year over year)
CREATE TABLE IF NOT EXISTS position_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    position INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE,
    UNIQUE(song_id, year)
);

CREATE INDEX IF NOT EXISTS idx_position_history_song ON position_history(song_id);
CREATE INDEX IF NOT EXISTS idx_position_history_year ON position_history(year);

-- Fun facts table
CREATE TABLE IF NOT EXISTS fun_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL,
    fact_text TEXT NOT NULL,
    fact_order INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_song_id ON fun_facts(song_id);

-- Playlist state table (singleton)
CREATE TABLE IF NOT EXISTS playlist_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_position INTEGER,
    current_song_id INTEGER,
    detected_at TIMESTAMP,
    npo_metadata TEXT,
    FOREIGN KEY (current_song_id) REFERENCES songs(id)
);

-- Notification rules table
CREATE TABLE IF NOT EXISTS notification_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL,
    match_pattern TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_enabled_rules ON notification_rules(enabled);

-- Notification settings table (singleton for global notification config)
CREATE TABLE IF NOT EXISTS notification_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    notification_targets TEXT,  -- JSON array of notify service names
    notify_current_song BOOLEAN DEFAULT 1,
    notify_upcoming_song BOOLEAN DEFAULT 0,
    upcoming_notify_positions TEXT,  -- JSON array of positions (e.g., [1,2,3])
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class DatabaseManager:
    """Manage SQLite database for Top 2000 data."""

    def __init__(self, db_path: Path):
        """Initialize database manager."""
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Initialize database with schema."""
        _LOGGER.debug("Initializing database at %s", self.db_path)

        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect and create schema
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()

        _LOGGER.info("Database initialized successfully")

    async def is_populated(self) -> bool:
        """Check if database has song data."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM songs") as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0
                return count > 0

    async def insert_song(
        self,
        position: int,
        artist: str,
        title: str,
        year: Optional[int] = None,
    ) -> int:
        """Insert a song into the database."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT OR REPLACE INTO songs (position, artist, title, year, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (position, artist, title, year, datetime.now()),
            )
            await db.commit()
            return cursor.lastrowid

    async def insert_fun_fact(
        self,
        song_id: int,
        fact_text: str,
        fact_order: int = 1,
    ) -> int:
        """Insert a fun fact for a song."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO fun_facts (song_id, fact_text, fact_order)
                VALUES (?, ?, ?)
                """,
                (song_id, fact_text, fact_order),
            )
            await db.commit()
            return cursor.lastrowid

    async def match_song(
        self,
        artist: str,
        title: str,
    ) -> Optional[dict]:
        """
        Match a song using fuzzy matching.

        Returns song data with fun facts if match found, None otherwise.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get all songs for fuzzy matching
            async with db.execute(
                "SELECT id, position, artist, title, year, cover_art_url, cover_art_cached_at FROM songs"
            ) as cursor:
                songs = await cursor.fetchall()

            best_match = None
            best_score = 0

            for song in songs:
                # Fuzzy match on both artist and title
                # Use partial_ratio for better substring matching (handles extras like "(Live)", "(Remastered)", etc.)
                artist_score = fuzz.partial_ratio(artist.lower(), song[2].lower())
                title_score = fuzz.partial_ratio(title.lower(), song[3].lower())

                # Combined score (weighted average)
                combined_score = (artist_score + title_score) / 2

                if combined_score > best_score and combined_score >= FUZZY_MATCH_THRESHOLD:
                    best_score = combined_score
                    best_match = {
                        "id": song[0],
                        "position": song[1],
                        "artist": song[2],
                        "title": song[3],
                        "year": song[4],
                        "cover_art_url": song[5],
                        "cover_art_cached_at": song[6],
                    }

            if best_match:
                _LOGGER.debug(
                    "Matched '%s - %s' to position %d (score: %.1f)",
                    artist,
                    title,
                    best_match["position"],
                    best_score,
                )

                # Get fun facts for the matched song
                async with db.execute(
                    "SELECT fact_text, fact_order FROM fun_facts WHERE song_id = ? ORDER BY fact_order",
                    (best_match["id"],),
                ) as cursor:
                    facts = await cursor.fetchall()
                    best_match["fun_facts"] = [fact[0] for fact in facts]

                # Get position history
                best_match["position_history"] = await self.get_position_history(best_match["id"])

                return best_match

            _LOGGER.warning(
                "No match found for '%s - %s' (best score: %.1f)",
                artist,
                title,
                best_score,
            )
            return None

    async def get_song_by_position(self, position: int) -> Optional[dict]:
        """Get song by position with fun facts."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, position, artist, title, year, cover_art_url, cover_art_cached_at FROM songs WHERE position = ?",
                (position,),
            ) as cursor:
                row = await cursor.fetchone()

                if not row:
                    return None

                song = {
                    "id": row[0],
                    "position": row[1],
                    "artist": row[2],
                    "title": row[3],
                    "year": row[4],
                    "cover_art_url": row[5],
                    "cover_art_cached_at": row[6],
                }

                # Get fun facts
                async with db.execute(
                    "SELECT fact_text, fact_order FROM fun_facts WHERE song_id = ? ORDER BY fact_order",
                    (song["id"],),
                ) as cursor:
                    facts = await cursor.fetchall()
                    song["fun_facts"] = [fact[0] for fact in facts]

                # Get position history
                song["position_history"] = await self.get_position_history(song["id"])

                return song

    async def get_song_by_artist_title(
        self, artist: str, title: str
    ) -> Optional[dict]:
        """Get song by exact artist and title match."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, position, artist, title, year, cover_art_url
                FROM songs
                WHERE LOWER(artist) = LOWER(?) AND LOWER(title) = LOWER(?)
                """,
                (artist, title),
            ) as cursor:
                row = await cursor.fetchone()

                if not row:
                    return None

                return {
                    "id": row[0],
                    "position": row[1],
                    "artist": row[2],
                    "title": row[3],
                    "year": row[4],
                    "cover_art_url": row[5],
                }

    async def get_upcoming_songs(
        self,
        current_position: int,
        count: int = 10,
    ) -> list[dict]:
        """Get upcoming songs based on current position.

        During Top 2000, songs count DOWN from 2000 to 1.
        So upcoming songs have LOWER position numbers.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, position, artist, title, year, cover_art_url
                FROM songs
                WHERE position < ?
                ORDER BY position DESC
                LIMIT ?
                """,
                (current_position, count),
            ) as cursor:
                rows = await cursor.fetchall()

                upcoming = []
                for row in rows:
                    song_data = {
                        "id": row[0],
                        "position": row[1],
                        "artist": row[2],
                        "title": row[3],
                        "year": row[4],
                        "cover_art_url": row[5],
                    }
                    # Get position history for each upcoming song
                    song_data["position_history"] = await self.get_position_history(row[0])
                    upcoming.append(song_data)

                return upcoming

    async def update_cover_art(
        self,
        song_id: int,
        cover_art_url: str,
        musicbrainz_id: Optional[str] = None,
    ) -> None:
        """Update cover art URL for a song."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE songs
                SET cover_art_url = ?, cover_art_cached_at = ?, musicbrainz_id = ?
                WHERE id = ?
                """,
                (cover_art_url, datetime.now(), musicbrainz_id, song_id),
            )
            await db.commit()

    async def is_cover_art_cached(self, song_id: int) -> bool:
        """Check if cover art is cached and still valid."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT cover_art_url, cover_art_cached_at FROM songs WHERE id = ?",
                (song_id,),
            ) as cursor:
                row = await cursor.fetchone()

                if not row or not row[0] or not row[1]:
                    return False

                # Check if cache is still valid
                cached_at = datetime.fromisoformat(row[1])
                cache_valid = datetime.now() - cached_at < timedelta(hours=CACHE_DURATION_HOURS)

                return cache_valid

    async def update_playlist_state(
        self,
        position: int,
        song_id: int,
        npo_metadata: str,
    ) -> None:
        """Update current playlist state (singleton row)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO playlist_state (id, current_position, current_song_id, detected_at, npo_metadata)
                VALUES (1, ?, ?, ?, ?)
                """,
                (position, song_id, datetime.now(), npo_metadata),
            )
            await db.commit()

    async def get_playlist_state(self) -> Optional[dict]:
        """Get current playlist state."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT current_position, current_song_id, detected_at, npo_metadata FROM playlist_state WHERE id = 1"
            ) as cursor:
                row = await cursor.fetchone()

                if not row:
                    return None

                return {
                    "current_position": row[0],
                    "current_song_id": row[1],
                    "detected_at": row[2],
                    "npo_metadata": row[3],
                }

    async def add_notification_rule(
        self,
        rule_type: str,
        match_pattern: str,
        enabled: bool = True,
    ) -> int:
        """Add a notification rule."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO notification_rules (rule_type, match_pattern, enabled)
                VALUES (?, ?, ?)
                """,
                (rule_type, match_pattern, enabled),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_notification_rules(self, enabled_only: bool = True) -> list[dict]:
        """Get all notification rules."""
        query = "SELECT id, rule_type, match_pattern, enabled FROM notification_rules"
        if enabled_only:
            query += " WHERE enabled = 1"

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()

                rules = []
                for row in rows:
                    rules.append({
                        "id": row[0],
                        "rule_type": row[1],
                        "match_pattern": row[2],
                        "enabled": bool(row[3]),
                    })

                return rules

    async def delete_notification_rule(self, rule_id: int) -> None:
        """Delete a notification rule."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM notification_rules WHERE id = ?",
                (rule_id,),
            )
            await db.commit()

    async def get_position_history(self, song_id: int, limit: int = 5) -> list[dict]:
        """
        Get position history for a song.

        Returns list of {year, position} dicts, ordered by year descending.
        Excludes current year (2025) to show historical trends only.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT year, position
                FROM position_history
                WHERE song_id = ? AND year < 2025
                ORDER BY year DESC
                LIMIT ?
                """,
                (song_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()

                history = []
                for row in rows:
                    history.append({
                        "year": row[0],
                        "position": row[1],
                    })

                return history

    async def add_position_history(
        self,
        song_id: int,
        year: int,
        position: int,
    ) -> None:
        """Add or update position history for a song."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO position_history (song_id, year, position)
                VALUES (?, ?, ?)
                """,
                (song_id, year, position),
            )
            await db.commit()

    async def get_notification_settings(self) -> dict:
        """
        Get notification settings.

        Returns dict with notification_targets, notify_current_song, etc.
        """
        import json

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT notification_targets, notify_current_song,
                       notify_upcoming_song, upcoming_notify_positions
                FROM notification_settings
                WHERE id = 1
                """
            ) as cursor:
                row = await cursor.fetchone()

                if not row:
                    # Return defaults if not configured
                    return {
                        "notification_targets": ["persistent_notification"],
                        "notify_current_song": True,
                        "notify_upcoming_song": False,
                        "upcoming_notify_positions": [1, 2, 3],
                    }

                return {
                    "notification_targets": json.loads(row[0]) if row[0] else ["persistent_notification"],
                    "notify_current_song": bool(row[1]),
                    "notify_upcoming_song": bool(row[2]),
                    "upcoming_notify_positions": json.loads(row[3]) if row[3] else [1, 2, 3],
                }

    async def update_notification_settings(
        self,
        notification_targets: list[str] | None = None,
        notify_current_song: bool | None = None,
        notify_upcoming_song: bool | None = None,
        upcoming_notify_positions: list[int] | None = None,
    ) -> None:
        """Update notification settings."""
        import json

        async with aiosqlite.connect(self.db_path) as db:
            # Build update query dynamically based on provided values
            updates = []
            params = []

            if notification_targets is not None:
                updates.append("notification_targets = ?")
                params.append(json.dumps(notification_targets))

            if notify_current_song is not None:
                updates.append("notify_current_song = ?")
                params.append(int(notify_current_song))

            if notify_upcoming_song is not None:
                updates.append("notify_upcoming_song = ?")
                params.append(int(notify_upcoming_song))

            if upcoming_notify_positions is not None:
                updates.append("upcoming_notify_positions = ?")
                params.append(json.dumps(upcoming_notify_positions))

            if not updates:
                return

            updates.append("updated_at = CURRENT_TIMESTAMP")

            # Try to update first, if no rows affected then insert
            query = f"UPDATE notification_settings SET {', '.join(updates)} WHERE id = 1"
            cursor = await db.execute(query, params)
            await db.commit()

            if cursor.rowcount == 0:
                # Insert initial row with defaults
                await db.execute(
                    """
                    INSERT INTO notification_settings
                    (id, notification_targets, notify_current_song,
                     notify_upcoming_song, upcoming_notify_positions)
                    VALUES (1, ?, ?, ?, ?)
                    """,
                    (
                        json.dumps(notification_targets or ["persistent_notification"]),
                        int(notify_current_song if notify_current_song is not None else True),
                        int(notify_upcoming_song if notify_upcoming_song is not None else False),
                        json.dumps(upcoming_notify_positions or [1, 2, 3]),
                    ),
                )
                await db.commit()

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
