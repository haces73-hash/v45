"""Fast, offline Swedish place lookup. Coordinates are approximate place centers."""
import json
import re
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "data" / "sweden_places.json").read_text(encoding="utf-8"))
MUNICIPALITIES = {}
MUNICIPALITY_CODES = {}
LOCALITIES = {}
for code, name, lat, lon in _DATA["municipalities"]:
    MUNICIPALITIES[name.casefold()] = (lat, lon)
    MUNICIPALITY_CODES[code] = name
for name, municipality, lat, lon in _DATA["localities"]:
    LOCALITIES.setdefault(name.casefold(), []).append((municipality.casefold(), (lat, lon)))
NAMES = set(MUNICIPALITIES) | set(LOCALITIES)
MAX_WORDS = max(len(name.split()) for name in NAMES)
_WORD = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_LABEL = re.compile(r"\b(?:arbetsort|stationeringsort|placering|arbetsplats)\s*[:\-]?\s*", re.I)

def normalize(value):
    value = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    value = re.sub(r"\s+kommun$", "", value)
    if value.endswith("s") and value[:-1] in MUNICIPALITIES:
        value = value[:-1]
    return value

def coordinates(value, municipality=None):
    name = normalize(value)
    if not name:
        return None
    if name in MUNICIPALITIES:
        return MUNICIPALITIES[name]
    places = LOCALITIES.get(name, ())
    if municipality:
        places = [p for p in places if p[0] == normalize(municipality)]
    unique = {point for _, point in places}
    return next(iter(unique)) if len(unique) == 1 else None

def municipality_from_code(value):
    return MUNICIPALITY_CODES.get(str(value or "").zfill(4), "")

def _find_name(text):
    words = _WORD.findall(str(text or "").casefold())
    for size in range(min(MAX_WORDS, len(words)), 0, -1):
        for i in range(len(words) - size + 1):
            candidate = " ".join(words[i:i+size])
            if candidate in NAMES:
                return candidate
            if candidate.endswith("s") and candidate[:-1] in MUNICIPALITIES and i+size < len(words) and words[i+size] == "kommun":
                return candidate[:-1]
    return ""

def find_in_title(title):
    return _find_name(title)

def find_labeled_workplace(description):
    text = str(description or "")
    for match in _LABEL.finditer(text):
        name = _find_name(text[match.end():match.end()+100].splitlines()[0])
        if name:
            return name
    return ""
