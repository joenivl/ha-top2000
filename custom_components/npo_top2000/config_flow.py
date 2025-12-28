"""Config flow for NPO Radio 2 Top 2000 integration."""
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback, HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_UPCOMING_COUNT,
    CONF_UPDATE_INTERVAL,
    CONF_ENABLE_NOTIFICATIONS,
    DEFAULT_UPCOMING_COUNT,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_ENABLE_NOTIFICATIONS,
    MIN_UPDATE_INTERVAL,
    MAX_UPDATE_INTERVAL,
    RULE_TYPE_ARTIST,
    RULE_TYPE_TITLE,
)

_LOGGER = logging.getLogger(__name__)


class Top2000ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NPO Top 2000."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            # Create entry
            return self.async_create_entry(
                title="NPO Radio 2 Top 2000",
                data=user_input,
            )

        # Show configuration form
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPCOMING_COUNT,
                    default=DEFAULT_UPCOMING_COUNT,
                ): vol.In([10, 20]),
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=DEFAULT_UPDATE_INTERVAL,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                ),
                vol.Optional(
                    CONF_ENABLE_NOTIFICATIONS,
                    default=DEFAULT_ENABLE_NOTIFICATIONS,
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "Top2000OptionsFlow":
        """Get the options flow for this handler."""
        return Top2000OptionsFlow()


class Top2000OptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for NPO Top 2000."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage notification rules."""
        return await self.async_step_menu()

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the menu for notification rules."""
        return self.async_show_menu(
            step_id="menu",
            menu_options=["notification_settings", "add_rule", "list_rules"],
        )

    async def async_step_notification_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure notification settings."""
        db_manager = self.hass.data[DOMAIN][self.config_entry.entry_id]["db_manager"]

        if user_input is not None:
            # Get all available notify services
            notify_services = user_input.get("notification_targets", "").split(",")
            notify_services = [s.strip() for s in notify_services if s.strip()]

            if not notify_services:
                notify_services = ["persistent_notification"]

            # Get upcoming positions
            upcoming_pos_str = user_input.get("upcoming_notify_positions", "1,2,3")
            try:
                upcoming_positions = [int(p.strip()) for p in upcoming_pos_str.split(",") if p.strip()]
            except ValueError:
                upcoming_positions = [1, 2, 3]

            # Update database
            await db_manager.update_notification_settings(
                notification_targets=notify_services,
                notify_current_song=user_input.get("notify_current_song", True),
                notify_upcoming_song=user_input.get("notify_upcoming_song", False),
                upcoming_notify_positions=upcoming_positions,
            )

            _LOGGER.info("Updated notification settings: targets=%s", notify_services)

            return self.async_create_entry(title="", data={})

        # Get current settings
        current_settings = await db_manager.get_notification_settings()

        # Show form
        data_schema = vol.Schema(
            {
                vol.Optional(
                    "notification_targets",
                    default=",".join(current_settings.get("notification_targets", ["persistent_notification"])),
                ): str,
                vol.Optional(
                    "notify_current_song",
                    default=current_settings.get("notify_current_song", True),
                ): bool,
                vol.Optional(
                    "notify_upcoming_song",
                    default=current_settings.get("notify_upcoming_song", False),
                ): bool,
                vol.Optional(
                    "upcoming_notify_positions",
                    default=",".join(map(str, current_settings.get("upcoming_notify_positions", [1, 2, 3]))),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="notification_settings",
            data_schema=data_schema,
            description_placeholders={
                "info": (
                    "Configure notification behavior:\n\n"
                    "• Notification targets: Comma-separated list of notify services (e.g., 'notify.mobile_app_iphone,persistent_notification')\n"
                    "• Notify current song: Send notifications for songs matching rules when they're playing NOW\n"
                    "• Notify upcoming song: Send notifications for songs matching rules that are COMING UP\n"
                    "• Upcoming positions: Which upcoming positions to check (e.g., '1,2,3' for next 3 songs)"
                )
            },
        )

    async def async_step_add_rule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new notification rule."""
        if user_input is not None:
            # Get database manager
            db_manager = self.hass.data[DOMAIN][self.config_entry.entry_id]["db_manager"]

            # Add rule to database
            await db_manager.add_notification_rule(
                rule_type=user_input["rule_type"],
                match_pattern=user_input["pattern"],
                enabled=True,
            )

            _LOGGER.info(
                "Added notification rule: %s = '%s'",
                user_input["rule_type"],
                user_input["pattern"],
            )

            return self.async_create_entry(title="", data={})

        # Show form to add rule
        data_schema = vol.Schema(
            {
                vol.Required("rule_type"): vol.In({
                    RULE_TYPE_ARTIST: "Artist",
                    RULE_TYPE_TITLE: "Title",
                }),
                vol.Required("pattern"): str,
            }
        )

        return self.async_show_form(
            step_id="add_rule",
            data_schema=data_schema,
            description_placeholders={
                "example": "Example: 'Queen' for artist or 'Bohemian Rhapsody' for title"
            },
        )

    async def async_step_list_rules(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """List and manage existing notification rules."""
        # Get database manager
        db_manager = self.hass.data[DOMAIN][self.config_entry.entry_id]["db_manager"]

        if user_input is not None:
            # Delete selected rule
            if "delete_rule_id" in user_input:
                await db_manager.delete_notification_rule(user_input["delete_rule_id"])
                _LOGGER.info("Deleted notification rule %d", user_input["delete_rule_id"])

            return self.async_create_entry(title="", data={})

        # Get all rules
        rules = await db_manager.get_notification_rules(enabled_only=False)

        if not rules:
            return self.async_show_form(
                step_id="list_rules",
                description_placeholders={
                    "rules_info": "No notification rules configured yet. Add one from the menu!"
                },
            )

        # Create description with all rules
        rules_text = "\n".join([
            f"• {rule['rule_type'].capitalize()}: '{rule['match_pattern']}' (ID: {rule['id']})"
            for rule in rules
        ])

        # Create schema to select rule to delete
        rule_choices = {
            rule["id"]: f"{rule['rule_type'].capitalize()}: {rule['match_pattern']}"
            for rule in rules
        }

        data_schema = vol.Schema(
            {
                vol.Optional("delete_rule_id"): vol.In(rule_choices),
            }
        )

        return self.async_show_form(
            step_id="list_rules",
            data_schema=data_schema,
            description_placeholders={
                "rules_info": f"Current notification rules:\n{rules_text}\n\nSelect a rule to delete (optional):"
            },
        )
