"""Un menu per ogni tasto di ogni Macroboard: sceglie la luce da comandare."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MacroboardConfigEntry
from .const import DOMAIN, NONE_OPTION, NUM_KEYS
from .manager import Board, MacroboardManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MacroboardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    manager = entry.runtime_data
    dev_reg = dr.async_get(hass)
    entities: list[KeySelect] = []
    for board in manager.boards.values():
        device = dev_reg.async_get(board.device_id)
        if device is None:
            continue
        for n in range(1, NUM_KEYS + 1):
            if n in board.keys:
                entities.append(KeySelect(manager, board, n, device))
    async_add_entities(entities)


class KeySelect(SelectEntity):
    """Luce assegnata a un tasto."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:lightbulb-on-outline"

    def __init__(self, manager: MacroboardManager, board: Board, key: int, device: dr.DeviceEntry) -> None:
        self._manager = manager
        self._board = board
        self._key = key
        self._attr_unique_id = f"{board.device_id}_key_{key}"
        self._attr_name = f"Tasto {key} luce"
        self._attr_translation_key = None
        # agganciato allo stesso dispositivo della board ESPHome
        self._attr_device_info = DeviceInfo(
            identifiers=device.identifiers, connections=device.connections
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._manager.add_listener(self._refresh))

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "macroboard_key": self._key,
            "macroboard_device": self._board.device_id,
            "macroboard_board": self._board.name,
            "macroboard_input": self._board.keys.get(self._key),
            "macroboard_status": self._board.status,
        }

    @property
    def options(self) -> list[str]:
        opts = [NONE_OPTION, *self._manager.lights()]
        current = self.current_option
        if current not in opts:
            opts.append(current)  # luce rimossa: resta visibile finché non la cambi
        return opts

    @property
    def current_option(self) -> str:
        return self._manager.label_for(self._manager.get_assignment(self._board.device_id, self._key))

    async def async_select_option(self, option: str) -> None:
        await self._manager.async_assign(self._board.device_id, self._key, option)
        self.async_write_ha_state()
