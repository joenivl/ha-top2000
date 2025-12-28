"""The NPO Radio 2 Top 2000 integration."""
import asyncio
import logging
from pathlib import Path

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, DB_NAME, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
from .coordinator import Top2000DataUpdateCoordinator
from .database import DatabaseManager
from .data_importer import import_top2000_data

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NPO Top 2000 from a config entry."""
    _LOGGER.info("Setting up NPO Top 2000 integration")

    # Initialize database in config directory (writable location)
    # Use config/.storage/npo_top2000/ instead of custom_components (read-only)
    db_dir = Path(hass.config.path(".storage", DOMAIN))
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / DB_NAME

    # If database doesn't exist in storage, copy it from integration folder
    if not db_path.exists():
        _LOGGER.info("First run: copying pre-populated database to storage")
        source_db = Path(__file__).parent / "data" / DB_NAME

        if source_db.exists():
            import shutil
            # Run blocking file copy in thread to avoid blocking event loop
            await asyncio.to_thread(shutil.copy2, source_db, db_path)
            _LOGGER.info("Database copied successfully from integration")
        else:
            _LOGGER.warning("Source database not found at %s, will create empty database", source_db)

    db_manager = DatabaseManager(db_path)

    try:
        await db_manager.initialize()

        # Verify database is populated
        if not await db_manager.is_populated():
            _LOGGER.warning("Database is empty after initialization")
            # Optionally: fall back to import if needed
            # success = await import_top2000_data(db_manager)
        else:
            _LOGGER.info("Database ready with Top 2000 data")

    except Exception as err:
        _LOGGER.error("Failed to initialize database: %s", err)
        return False

    # Get aiohttp session
    session = async_get_clientsession(hass)

    # Create coordinator
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator = Top2000DataUpdateCoordinator(
        hass,
        session,
        db_manager,
        update_interval=update_interval,
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator and db_manager
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "db_manager": db_manager,
    }

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("NPO Top 2000 integration setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading NPO Top 2000 integration")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up database connection
        data = hass.data[DOMAIN].pop(entry.entry_id)
        db_manager: DatabaseManager = data["db_manager"]
        await db_manager.close()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
