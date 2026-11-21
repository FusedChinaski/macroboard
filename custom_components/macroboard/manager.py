"""Trova le Macroboard, tiene le assegnazioni e fa reagire tasti e manopola."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
import time
from typing import Callable

from homeassistant.const import EVENT_STATE_CHANGED, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.storage import Store

from .const import (
    KNOB_STEP_PCT,
    LABEL_MAX,
    NONE_OPTION,
    NUM_KEYS,
    PANEL_URL,
    SHORT_PRESS_MAX_S,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# Le entità ESPHome si riconoscono dal nome dell'oggetto (fine di unique_id / entity_id)
_RE_KEY = re.compile(r"(?:^|[-_.])tasto_(\d)$")
_RE_LABEL = re.compile(r"(?:^|[-_.])etichetta_(\d)$")
_RE_CFG = re.compile(r"(?:^|[-_.])indirizzo_configurazione$")
_RE_KNOB = re.compile(r"(?:^|[-_.])manopola$")
_RE_KNOB_BTN = re.compile(r"(?:^|[-_.])pulsante_manopola$")


def _match(entry: er.RegistryEntry, regex: re.Pattern) -> re.Match | None:
    return regex.search(entry.unique_id or "") or regex.search(entry.entity_id)


@dataclass
class Board:
    """Una Macroboard fisica."""

    device_id: str
    name: str
    keys: dict[int, str] = field(default_factory=dict)      # n -> binary_sensor
    labels: dict[int, str] = field(default_factory=dict)    # n -> text
    config_text: str | None = None
    knob: str | None = None
    knob_btn: str | None = None
    last_light: str | None = None
    btn_pressed_at: float = 0.0


class MacroboardManager:
    """Cuore dell'integrazione."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        # device_id -> {"1": "light.x", ...}
        self.assignments: dict[str, dict[str, str]] = {}
        self.boards: dict[str, Board] = {}
        self._unsubs: list[Callable[[], None]] = []
        self._listeners: list[Callable[[], None]] = []  # select da aggiornare
        self._light_cache: dict[str, str] | None = None

    # ------------------------------------------------------------------ setup
    async def async_load(self) -> None:
        self.assignments = await self._store.async_load() or {}
        self.discover()
        self._subscribe()

    def discover(self) -> None:
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        by_device: dict[str, list[er.RegistryEntry]] = {}
        for entry in ent_reg.entities.values():
            if entry.platform == "esphome" and entry.device_id:
                by_device.setdefault(entry.device_id, []).append(entry)

        boards: dict[str, Board] = {}
        for device_id, entries in by_device.items():
            if not any(e.domain == "text" and _match(e, _RE_CFG) for e in entries):
                continue
            device = dev_reg.async_get(device_id)
            name = (device.name_by_user or device.name) if device else "Macroboard"
            board = self.boards.get(device_id) or Board(device_id, name or "Macroboard")
            board.name = name or "Macroboard"
            for e in entries:
                if e.domain == "binary_sensor" and (m := _match(e, _RE_KEY)):
                    board.keys[int(m.group(1))] = e.entity_id
                elif e.domain == "binary_sensor" and _match(e, _RE_KNOB_BTN):
                    board.knob_btn = e.entity_id
                elif e.domain == "sensor" and _match(e, _RE_KNOB):
                    board.knob = e.entity_id
                elif e.domain == "text" and (m := _match(e, _RE_LABEL)):
                    board.labels[int(m.group(1))] = e.entity_id
                elif e.domain == "text" and _match(e, _RE_CFG):
                    board.config_text = e.entity_id
            boards[device_id] = board
        self.boards = boards
        self._light_cache = None
        for b in boards.values():
            _LOGGER.info("Macroboard trovata: %s | tasti=%s manopola=%s pulsante=%s qr=%s",
                         b.name, b.keys, b.knob, b.knob_btn, b.config_text)
        if not boards:
            _LOGGER.info("Nessuna Macroboard trovata")

    def _subscribe(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        watched: list[str] = []
        for b in self.boards.values():
            watched += list(b.keys.values())
            watched += [x for x in (b.knob, b.knob_btn, b.config_text) if x]
            watched += list(b.labels.values())
        _LOGGER.info("Macroboard: in ascolto su %d entità", len(watched))
        if watched:
            self._unsubs.append(
                async_track_state_change_event(self.hass, watched, self._on_board_event)
            )
        self._unsubs.append(self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._on_any_state))

    async def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    # ------------------------------------------------------------------ luci
    def lights(self) -> dict[str, str]:
        """Etichetta leggibile -> entity_id, escluse le luci delle Macroboard."""
        if self._light_cache is not None:
            return self._light_cache
        ent_reg = er.async_get(self.hass)
        found: list[tuple[str, str]] = []
        for state in self.hass.states.async_all("light"):
            entry = ent_reg.async_get(state.entity_id)
            if entry and entry.device_id in self.boards:
                continue
            found.append((state.name or state.entity_id, state.entity_id))
        names = [n for n, _ in found]
        result: dict[str, str] = {}
        for name, eid in sorted(found, key=lambda x: x[0].lower()):
            label = name if names.count(name) == 1 else f"{name} ({eid})"
            result[label] = eid
        self._light_cache = result
        return result

    def label_for(self, entity_id: str | None) -> str:
        if not entity_id:
            return NONE_OPTION
        for label, eid in self.lights().items():
            if eid == entity_id:
                return label
        state = self.hass.states.get(entity_id)
        return state.name if state else entity_id

    def get_assignment(self, device_id: str, key: int) -> str | None:
        return self.assignments.get(device_id, {}).get(str(key))

    async def async_assign(self, device_id: str, key: int, option: str) -> None:
        board_map = self.assignments.setdefault(device_id, {})
        if option == NONE_OPTION:
            board_map.pop(str(key), None)
        else:
            entity_id = self.lights().get(option)
            if entity_id is None:
                raise ValueError(f"Luce sconosciuta: {option}")
            board_map[str(key)] = entity_id
        await self._store.async_save(self.assignments)
        if board := self.boards.get(device_id):
            await self._push_labels(board)

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    # ------------------------------------------------------------------ eventi
    @callback
    def _on_any_state(self, event: Event) -> None:
        """Aggiorna i menu quando una luce compare, sparisce o cambia nome."""
        eid: str = event.data["entity_id"]
        if not eid.startswith("light."):
            return
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if old is not None and new is not None and old.name == new.name:
            return
        self._light_cache = None
        for cb in list(self._listeners):
            cb()

    @callback
    def _on_board_event(self, event: Event) -> None:
        eid: str = event.data["entity_id"]
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if new is None:
            return
        _LOGGER.info("Macroboard evento: %s %s -> %s", eid, old.state if old else None, new.state)
        for board in self.boards.values():
            # la board è tornata online: rimanda indirizzo QR ed etichette
            if eid in (board.config_text, *board.labels.values()):
                if old is None or old.state == STATE_UNAVAILABLE:
                    if new.state != STATE_UNAVAILABLE:
                        self.hass.async_create_task(self.async_push_board(board))
                return
            for n, key_eid in board.keys.items():
                if key_eid == eid and new.state == "on" and old is not None and old.state == "off":
                    self.hass.async_create_task(self._press_key(board, n))
                    return
            if eid == board.knob:
                self._turn_knob(board, old, new)
                return
            if eid == board.knob_btn:
                self._knob_button(board, old, new)
                return

    async def _press_key(self, board: Board, n: int) -> None:
        light = self.get_assignment(board.device_id, n)
        _LOGGER.info("Macroboard %s: tasto %s -> %s", board.name, n, light)
        if not light:
            return
        board.last_light = light
        try:
            await self.hass.services.async_call("light", "toggle", {"entity_id": light}, blocking=True)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Macroboard: impossibile commutare %s", light)

    def _target(self, board: Board) -> str | None:
        if board.last_light:
            return board.last_light
        for n in range(1, NUM_KEYS + 1):
            if light := self.get_assignment(board.device_id, n):
                return light
        return None

    @callback
    def _turn_knob(self, board: Board, old, new) -> None:
        bad = (STATE_UNAVAILABLE, STATE_UNKNOWN)
        if old is None or old.state in bad or new.state in bad:
            return
        try:
            delta = float(new.state) - float(old.state)
        except ValueError:
            return
        target = self._target(board)
        if not target or delta == 0:
            return
        step = max(-100, min(100, int(delta * KNOB_STEP_PCT)))
        self.hass.async_create_task(
            self.hass.services.async_call(
                "light", "turn_on", {"entity_id": target, "brightness_step_pct": step}
            )
        )

    @callback
    def _knob_button(self, board: Board, old, new) -> None:
        if new.state == "on":
            board.btn_pressed_at = time.monotonic()
        elif new.state == "off" and old is not None and old.state == "on":
            if time.monotonic() - board.btn_pressed_at < SHORT_PRESS_MAX_S:
                if target := self._target(board):
                    self.hass.async_create_task(
                        self.hass.services.async_call("light", "toggle", {"entity_id": target})
                    )

    # ------------------------------------------------------------------ verso la board
    def config_url(self, board: Board) -> str:
        try:
            base = get_url(self.hass, prefer_external=False, allow_cloud=False)
        except NoURLAvailableError:
            base = "http://homeassistant.local:8123"
        return f"{base.rstrip('/')}/{PANEL_URL}?b={board.device_id}"

    async def _set_text(self, entity_id: str | None, value: str) -> None:
        if not entity_id:
            return
        state = self.hass.states.get(entity_id)
        if state is None or state.state == STATE_UNAVAILABLE or state.state == value:
            return
        await self.hass.services.async_call(
            "text", "set_value", {"entity_id": entity_id, "value": value}, blocking=False
        )

    async def _push_labels(self, board: Board) -> None:
        for n, text_eid in board.labels.items():
            light = self.get_assignment(board.device_id, n)
            label = self.label_for(light) if light else ""
            await self._set_text(text_eid, label[:LABEL_MAX])

    async def async_push_board(self, board: Board) -> None:
        await self._set_text(board.config_text, self.config_url(board))
        await self._push_labels(board)

    async def async_push_all(self) -> None:
        for board in self.boards.values():
            await self.async_push_board(board)
