"""Costanti dell'integrazione Macroboard."""

DOMAIN = "macroboard"
STORAGE_KEY = "macroboard.assignments"
STORAGE_VERSION = 1

NUM_KEYS = 6
NUM_PAGES = 2
NONE_OPTION = "Nessuna"

PANEL_URL = "macroboard"
STATIC_URL = "/macroboard_static"
PANEL_COMPONENT = "macroboard-panel"

KNOB_STEP_PCT = 5
LABEL_MAX = 18

# cosa si può assegnare a un tasto
TOGGLE_DOMAINS = ("light", "switch", "fan", "input_boolean")   # premi = accendi/spegni
ACTIVATE_DOMAINS = ("scene", "script")                         # premi = attiva
DOMAIN_SUFFIX = {
    "switch": "presa",
    "fan": "ventilatore",
    "input_boolean": "interruttore",
    "scene": "scena",
    "script": "script",
}

SERVICE_SET_PAGE_NAME = "set_page_name"
