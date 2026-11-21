"""Macroboard: collega in automatico le pulsantiere Macroboard (ESPHome) alle luci di casa."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.start import async_at_started

from .const import DOMAIN, PANEL_COMPONENT, PANEL_URL, STATIC_URL
from .manager import MacroboardManager

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SELECT]

type MacroboardConfigEntry = ConfigEntry[MacroboardManager]


async def _async_register_panel(hass: HomeAssistant) -> None:
    if not hass.data.get(f"{DOMAIN}_static"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)]
        )
        hass.data[f"{DOMAIN}_static"] = True
    if PANEL_URL not in hass.data.get(frontend.DATA_PANELS, {}):
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name=PANEL_COMPONENT,
            module_url=f"{STATIC_URL}/macroboard-panel.js?v=1.0.2",
            sidebar_title="Macroboard",
            sidebar_icon="mdi:gesture-tap-button",
            require_admin=False,
        )


async def async_setup_entry(hass: HomeAssistant, entry: MacroboardConfigEntry) -> bool:
    manager = MacroboardManager(hass)
    await manager.async_load()
    entry.runtime_data = manager

    await _async_register_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Una nuova Macroboard aggiunta in ESPHome -> ricarica per creare i suoi menu
    known = set(manager.boards)
    reload_pending: list = []

    @callback
    def _registry_updated(event: Event) -> None:
        if event.data.get("action") != "create" or reload_pending:
            return
        ent = er.async_get(hass).async_get(event.data["entity_id"])
        if not ent or ent.platform != "esphome" or ent.domain != "text":
            return
        if not ent.entity_id.endswith("indirizzo_configurazione"):
            return
        if ent.device_id in known:
            return

        @callback
        def _reload(_now) -> None:
            hass.config_entries.async_schedule_reload(entry.entry_id)

        reload_pending.append(async_call_later(hass, 5, _reload))

    entry.async_on_unload(
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _registry_updated)
    )
    entry.async_on_unload(lambda: [u() for u in reload_pending])

    # Manda indirizzo QR ed etichette alle board
    async def _push(_hass: HomeAssistant) -> None:
        await manager.async_push_all()

    entry.async_on_unload(async_at_started(hass, _push))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MacroboardConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_unload()
        frontend.async_remove_panel(hass, PANEL_URL)
    return ok
