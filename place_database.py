"""Offline Swedish place lookup. Municipality centers are approximations, not workplace coordinates."""
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
NAMES = sorted(set(MUNICIPALITIES) | set(LOCALITIES), key=len, reverse=True)

def normalize(value):
    text = re.sub(r"\\s+", " ", str(value or "").strip()).casefold()
    text = re.sub(r"\\s+kommun$", "", text)
    if text.endswith("s") and text[:-1] in MUNICIPALITIES:
        text = text[:-1]
    return text

def coordinates(value, municipality=None):
    name = normalize(value)
    if not name:
        return None
    if name in MUNICIPALITIES:
        return MUNICIPALITIES[name]
    places = LOCALITIES.get(name, [])
    if municipality:
        places = [p for p in places if p[0] == normalize(municipality)]
    unique = set(point for _, point in places)
    return next(iter(unique)) if len(unique) == 1 else None

def municipality_from_code(value):
    return MUNICIPALITY_CODES.get(str(value or "").zfill(4), "")

def find_in_title(title):
    """Match whole place names, including 'Borgholms kommun', longest first."""
    title = str(title or "").casefold()
    for name in NAMES:
        if re.search(r"(?<!\\w)" + re.escape(name) + r"(?:s(?=\\s+kommun)|(?=\\W|$))", title):
            return name
    return ""

def find_labeled_workplace(description):
    """Only use explicit workplace labels; incidental city mentions are unsafe."""
    text = str(description or "").casefold()
    for match in re.finditer(r"\\b(?:arbetsort|stationeringsort|placering|arbetsplats)\\s*[:\\-]?\\s*", text):
        snippet = text[match.end():match.end()+90]
        for name in NAMES:
            if re.match(re.escape(name) + r"(?:s(?=\\s+kommun)|(?=\\W|$))", snippet):
                return name
    return ""
