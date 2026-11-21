"""Trova le Macroboard, tiene le assegnazioni e fa reagire tasti e manopola."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
import re
from typing import Any, Callable

from homeassistant.const import EVENT_STATE_CHANGED, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.storage import Store

from .const import (
    KNOB_STEP_PCT,
    LABEL_MAX,
    NONE_OPTION,
    NUM_KEYS,
    NUM_PAGES,
    PANEL_URL,
    STORAGE_KEY,
    STORAGE_VERSION,
    TOGGLE_DOMAINS,
    ACTIVATE_DOMAINS,
    DOMAIN_SUFFIX,
)

_LOGGER = logging.getLogger(__name__)

# Le entità ESPHome si riconoscono dal nome dell'oggetto (fine di unique_id / entity_id)
def _rx(name: str) -> re.Pattern:
    return re.compile(rf"(?:^|[-_.]){name}$")

_RE_KEY = re.compile(r"(?:^|[-_.])tasto_(\d)$")
_RE_LABEL = re.compile(r"(?:^|[-_.])etichetta_(\d)$")
_RE_DATA = re.compile(r"(?:^|[-_.])dati_pagina_(\d)$")
_RE_CFG = _rx("indirizzo_configurazione")
_RE_KNOB = _rx("manopola")
_RE_KNOB_BTN = _rx("pulsante_manopola")
_RE_PAGE = _rx("pagina_attiva")
_RE_NUMKEYS = _rx("numero_tasti")
_RE_PAGENAMES = _rx("nomi_pagine")


def _match(entry: er.RegistryEntry, regex: re.Pattern) -> re.Match | None:
    return regex.search(entry.unique_id or "") or regex.search(entry.entity_id)


def _clean(text: str) -> str:
    return text.replace("|", "/").replace(";", ",").strip()[:LABEL_MAX]


@dataclass
class Board:
    """Una Macroboard fisica."""

    device_id: str
    name: str
    keys: dict[int, str] = field(default_factory=dict)      # n -> binary_sensor
    labels: dict[int, str] = field(default_factory=dict)    # n -> text (firmware 1.0)
    data: dict[int, str] = field(default_factory=dict)      # pagina -> text "Dati pagina N"
    config_text: str | None = None
    knob: str | None = None
    knob_btn: str | None = None
    page_sensor: str | None = None
    num_keys_entity: str | None = None
    names_text: str | None = None
    last_entity: str | None = None
    status: str = "Nessuna pressione ricevuta da Home Assistant"

    def all_entities(self) -> list[str]:
        out = [*self.keys.values(), *self.labels.values(), *self.data.values()]
        out += [x for x in (self.config_text, self.knob, self.knob_btn, self.page_sensor,
                            self.num_keys_entity, self.names_text) if x]
        return out


class MacroboardManager:
    """Cuore dell'integrazione."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        # device_id -> {"1": {"1": "light.x"}, "2": {...}}
        self.assignments: dict[str, dict[str, dict[str, str]]] = {}
        # device_id -> ["Luci", "PC"]
        self.page_names: dict[str, list[str]] = {}
        self.boards: dict[str, Board] = {}
        self._unsubs: list[Callable[[], None]] = []
        self._listeners: list[Callable[[], None]] = []
        self._option_cache: dict[str, str] | None = None
        self._push_pending: dict[str, Callable[[], None]] = {}

    # ------------------------------------------------------------------ setup / dati salvati
    async def async_load(self) -> None:
        raw = await self._store.async_load() or {}
        if "assignments" in raw or "page_names" in raw:
            self.assignments = raw.get("assignments", {})
            self.page_names = raw.get("page_names", {})
        else:  # formato 1.0: {device: {"1": "light.x"}} -> tutto in pagina 1
            self.assignments = {
                dev: {"1": {k: v for k, v in keys.items() if isinstance(v, str)}}
                for dev, keys in raw.items()
                if isinstance(keys, dict)
            }
        self.discover()
        self._subscribe()

    async def _save(self) -> None:
        await self._store.async_save(
            {"assignments": self.assignments, "page_names": self.page_names}
        )

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
            name = ((device.name_by_user or device.name) if device else None) or "Macroboard"
            old = self.boards.get(device_id)
            board = Board(device_id, name)
            if old:
                board.last_entity, board.status = old.last_entity, old.status
            for e in entries:
                if e.domain == "binary_sensor" and (m := _match(e, _RE_KEY)):
                    board.keys[int(m.group(1))] = e.entity_id
                elif e.domain == "binary_sensor" and _match(e, _RE_KNOB_BTN):
                    board.knob_btn = e.entity_id
                elif e.domain == "sensor" and _match(e, _RE_PAGE):
                    board.page_sensor = e.entity_id
                elif e.domain == "sensor" and _match(e, _RE_KNOB):
                    board.knob = e.entity_id
                elif e.domain == "number" and _match(e, _RE_NUMKEYS):
                    board.num_keys_entity = e.entity_id
                elif e.domain == "text" and (m := _match(e, _RE_DATA)):
                    board.data[int(m.group(1))] = e.entity_id
                elif e.domain == "text" and (m := _match(e, _RE_LABEL)):
                    board.labels[int(m.group(1))] = e.entity_id
                elif e.domain == "text" and _match(e, _RE_PAGENAMES):
                    board.names_text = e.entity_id
                elif e.domain == "text" and _match(e, _RE_CFG):
                    board.config_text = e.entity_id
            boards[device_id] = board
            _LOGGER.info("Macroboard trovata: %s | tasti=%s pagina=%s dati=%s",
                         board.name, board.keys, board.page_sensor, board.data)
        self.boards = boards
        self._option_cache = None

    def _subscribe(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        watched = [eid for b in self.boards.values() for eid in b.all_entities()]
        if watched:
            self._unsubs.append(
                async_track_state_change_event(self.hass, watched, self._on_board_event)
            )
        self._unsubs.append(self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._on_any_state))

    async def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        for cancel in self._push_pending.values():
            cancel()
        self._push_pending = {}

    # ------------------------------------------------------------------ cose assegnabili
    def options(self) -> dict[str, str]:
        """Etichetta leggibile -> entity_id (luci, prese, scene, script...)."""
        if self._option_cache is not None:
            return self._option_cache
        ent_reg = er.async_get(self.hass)
        found: list[tuple[str, str]] = []
        for domain in (*TOGGLE_DOMAINS, *ACTIVATE_DOMAINS):
            for state in self.hass.states.async_all(domain):
                entry = ent_reg.async_get(state.entity_id)
                if entry and (entry.device_id in self.boards or entry.platform == "macroboard"):
                    continue
                if entry and entry.hidden_by:
                    continue
                label = state.name or state.entity_id
                if suffix := DOMAIN_SUFFIX.get(domain):
                    label = f"{label} ({suffix})"
                found.append((label, state.entity_id))
        labels = [n for n, _ in found]
        result: dict[str, str] = {}
        for label, eid in sorted(found, key=lambda x: (not x[1].startswith("light."), x[0].lower())):
            result[label if labels.count(label) == 1 else f"{label} [{eid}]"] = eid
        self._option_cache = result
        return result

    def label_for(self, entity_id: str | None) -> str:
        if not entity_id:
            return NONE_OPTION
        for label, eid in self.options().items():
            if eid == entity_id:
                return label
        state = self.hass.states.get(entity_id)
        return state.name if state else entity_id

    def get_assignment(self, device_id: str, page: int, key: int) -> str | None:
        return self.assignments.get(device_id, {}).get(str(page), {}).get(str(key))

    def get_page_name(self, device_id: str, page: int) -> str:
        names = self.page_names.get(device_id) or []
        if len(names) >= page and names[page - 1]:
            return names[page - 1]
        return "Luci" if page == 1 else "Pagina 2"

    def num_keys(self, board: Board) -> int:
        if board.num_keys_entity and (st := self.hass.states.get(board.num_keys_entity)):
            try:
                return 6 if float(st.state) >= 6 else 3
            except ValueError:
                pass
        return NUM_KEYS if not board.page_sensor else 3

    def current_page(self, board: Board) -> int:
        if board.page_sensor and (st := self.hass.states.get(board.page_sensor)):
            try:
                return 2 if float(st.state) >= 2 else 1
            except ValueError:
                pass
        return 1

    async def async_assign(self, device_id: str, page: int, key: int, option: str) -> None:
        page_map = self.assignments.setdefault(device_id, {}).setdefault(str(page), {})
        if option == NONE_OPTION:
            page_map.pop(str(key), None)
        else:
            entity_id = self.options().get(option)
            if entity_id is None:
                raise ValueError(f"Elemento sconosciuto: {option}")
            page_map[str(key)] = entity_id
        await self._save()
        if board := self.boards.get(device_id):
            await self.async_push_board(board)

    async def async_set_page_name(self, device_id: str, page: int, name: str) -> None:
        names = self.page_names.setdefault(device_id, ["Luci", "Pagina 2"])
        while len(names) < NUM_PAGES:
            names.append(f"Pagina {len(names) + 1}")
        names[page - 1] = _clean(name) or ("Luci" if page == 1 else "Pagina 2")
        await self._save()
        self._notify()
        if board := self.boards.get(device_id):
            await self.async_push_board(board)

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    def _set_status(self, board: Board, text: str) -> None:
        board.status = f"{datetime.now().strftime('%H:%M:%S')} – {text}"
        _LOGGER.info("Macroboard %s: %s", board.name, text)
        self._notify()

    # ------------------------------------------------------------------ eventi
    @callback
    def _on_any_state(self, event: Event) -> None:
        eid: str = event.data["entity_id"]
        domain = eid.split(".", 1)[0]
        if domain not in TOGGLE_DOMAINS and domain not in ACTIVATE_DOMAINS:
            return
        old, new = event.data.get("old_state"), event.data.get("new_state")
        # comparsa / sparizione / cambio nome -> aggiorna i menu
        if old is None or new is None or old.name != new.name:
            self._option_cache = None
            self._notify()
        # una cosa assegnata ha cambiato stato -> aggiorna il display delle board
        for device_id, pages in self.assignments.items():
            if any(eid in keys.values() for keys in pages.values()):
                if board := self.boards.get(device_id):
                    self._schedule_push(board)

    @callback
    def _schedule_push(self, board: Board) -> None:
        if board.device_id in self._push_pending:
            return

        @callback
        def _run(_now) -> None:
            self._push_pending.pop(board.device_id, None)
            self.hass.async_create_task(self.async_push_board(board))

        self._push_pending[board.device_id] = async_call_later(self.hass, 0.3, _run)

    @callback
    def _on_board_event(self, event: Event) -> None:
        eid: str = event.data["entity_id"]
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if new is None:
            return
        for board in self.boards.values():
            if eid not in board.all_entities():
                continue
            # la board è tornata online: rimanda tutto
            if eid in (board.config_text, board.names_text, *board.data.values(), *board.labels.values()):
                if (old is None or old.state == STATE_UNAVAILABLE) and new.state != STATE_UNAVAILABLE:
                    self._schedule_push(board)
                return
            if eid in (board.num_keys_entity, board.page_sensor):
                board.last_entity = None
                self._notify()
                return
            for n, key_eid in board.keys.items():
                if key_eid == eid:
                    if new.state == STATE_ON and (old is None or old.state != STATE_ON):
                        self.hass.async_create_task(self._press_key(board, n))
                    return
            if eid == board.knob:
                self._turn_knob(board, old, new)
            return

    async def _press_key(self, board: Board, n: int) -> None:
        page = self.current_page(board)
        target = self.get_assignment(board.device_id, page, n)
        if not target:
            self._set_status(board, f"Pagina {page}, tasto {n}: nessuna azione assegnata")
            return
        state = self.hass.states.get(target)
        if state is None or state.state == STATE_UNAVAILABLE:
            self._set_status(board, f"Pagina {page}, tasto {n}: {target} non disponibile")
            return
        domain = target.split(".", 1)[0]
        service = "turn_on" if domain in ACTIVATE_DOMAINS else "toggle"
        if domain == "light":
            board.last_entity = target
        try:
            await self.hass.services.async_call(domain, service, {"entity_id": target}, blocking=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Macroboard: errore su %s", target)
            self._set_status(board, f"Tasto {n}: errore su {target}: {err}")
            return
        after = self.hass.states.get(target)
        self._set_status(board, f"Pagina {page}, tasto {n} → {state.name}: {after.state if after else '?'}")

    def _knob_target(self, board: Board) -> str | None:
        if board.last_entity:
            return board.last_entity
        page = self.current_page(board)
        for n in range(1, NUM_KEYS + 1):
            target = self.get_assignment(board.device_id, page, n)
            if target and target.startswith("light."):
                return target
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
        target = self._knob_target(board)
        if not target or delta == 0:
            return
        step = max(-100, min(100, int(delta * KNOB_STEP_PCT)))
        self.hass.async_create_task(
            self.hass.services.async_call(
                "light", "turn_on", {"entity_id": target, "brightness_step_pct": step}
            )
        )

    # ------------------------------------------------------------------ verso la board
    def config_url(self, board: Board) -> str:
        try:
            base = get_url(self.hass, prefer_external=False, allow_cloud=False)
        except NoURLAvailableError:
            base = "http://homeassistant.local:8123"
        return f"{base.rstrip('/')}/{PANEL_URL}?b={board.device_id}"

    def _key_block(self, entity_id: str | None) -> str:
        if not entity_id:
            return ""
        state = self.hass.states.get(entity_id)
        name = _clean(state.name if state else entity_id)
        domain = entity_id.split(".", 1)[0]
        if domain in ACTIVATE_DOMAINS:
            return f"{name}|0|-1|s"
        on = 1 if state is not None and state.state == STATE_ON else 0
        bri = -1
        if domain == "light" and state is not None:
            modes = state.attributes.get("supported_color_modes") or []
            dimmable = any(m != "onoff" for m in modes) or state.attributes.get("brightness") is not None
            if dimmable:
                b = state.attributes.get("brightness")
                bri = round((b or 0) * 100 / 255) if on else 0
        return f"{name}|{on}|{bri}|t"

    def data_string(self, board: Board, page: int) -> str:
        return ";".join(
            self._key_block(self.get_assignment(board.device_id, page, n))
            for n in range(1, NUM_KEYS + 1)
        )

    async def _set_text(self, entity_id: str | None, value: str) -> None:
        if not entity_id:
            return
        state = self.hass.states.get(entity_id)
        if state is None or state.state == STATE_UNAVAILABLE or state.state == value:
            return
        await self.hass.services.async_call(
            "text", "set_value", {"entity_id": entity_id, "value": value}, blocking=False
        )

    async def async_push_board(self, board: Board) -> None:
        await self._set_text(board.config_text, self.config_url(board))
        for page, text_eid in board.data.items():
            await self._set_text(text_eid, self.data_string(board, page))
        await self._set_text(
            board.names_text,
            f"{self.get_page_name(board.device_id, 1)}|{self.get_page_name(board.device_id, 2)}",
        )
        for n, text_eid in board.labels.items():  # firmware 1.0
            target = self.get_assignment(board.device_id, 1, n)
            await self._set_text(text_eid, self.label_for(target)[:LABEL_MAX] if target else "")

    async def async_push_all(self) -> None:
        for board in self.boards.values():
            await self.async_push_board(board)

    def board_info(self, board: Board) -> dict[str, Any]:
        return {
            "macroboard_board": board.name,
            "macroboard_status": board.status,
            "macroboard_num_keys": self.num_keys(board),
            "macroboard_num_keys_entity": board.num_keys_entity,
            "macroboard_current_page": self.current_page(board),
            "macroboard_page_names": [self.get_page_name(board.device_id, p) for p in range(1, NUM_PAGES + 1)],
        }
