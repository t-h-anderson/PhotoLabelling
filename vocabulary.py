import json
import re
from pathlib import Path
from collections import Counter
from PIL import Image
from config import OUTPUT_DIR, PHOTO_DIR, EXTENSIONS

_GPS_IFD_TAG = 34853  # EXIF tag for GPS sub-IFD


def _dms_to_decimal(dms, ref: str) -> float:
    degrees = float(dms[0])
    minutes = float(dms[1]) / 60
    seconds = float(dms[2]) / 3600
    decimal = degrees + minutes + seconds
    if ref in ("S", "W"):
        decimal = -decimal
    return round(decimal, 6)


def extract_gps(image_path: Path) -> tuple[float, float] | None:
    """Return (latitude, longitude) in decimal degrees from EXIF GPS data, or None."""
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if not exif:
                return None
            gps_ifd = exif.get_ifd(_GPS_IFD_TAG)
            if not gps_ifd:
                return None
            lat_ref = gps_ifd.get(1)
            lat = gps_ifd.get(2)
            lon_ref = gps_ifd.get(3)
            lon = gps_ifd.get(4)
            if not all([lat_ref, lat, lon_ref, lon]):
                return None
            return _dms_to_decimal(lat, lat_ref), _dms_to_decimal(lon, lon_ref)
    except Exception:
        return None

VOCABULARY_FILE = OUTPUT_DIR / "vocabulary.json"
BLACKLIST_FILE = OUTPUT_DIR / "blacklist.txt"

def event_from_path(path: Path) -> str | None:
    """
    Extract a human-readable event name from the folder immediately after
    the first 4-digit year component in the path, then strip any leading
    date prefix so only the event name remains.

    Handled prefix forms:
      "07.31 - Italy and Sofia"  →  "Italy and Sofia"
      "12 - Valencia"            →  "Valencia"
      "Thermal"                  →  "Thermal"

    Returns None if no year component is found or the folder name is empty
    after stripping.
    """
    parts = Path(path).parts
    for i, part in enumerate(parts[:-1]):  # last part is the filename
        if re.fullmatch(r"\d{4}", part):
            event_folder = parts[i + 1]
            # Strip optional "mm.dd - " or "mm - " date prefix
            name = re.sub(r"^\d{1,2}(?:\.\d{1,2})?\s*-\s*", "", event_folder).strip()
            return name or None
    return None


def scan_photos() -> list[Path]:
    return [p for p in PHOTO_DIR.rglob("*") if p.suffix.lower() in EXTENSIONS]

def load_vocabulary() -> Counter:
    if not VOCABULARY_FILE.exists():
        return Counter()
    content = VOCABULARY_FILE.read_text().strip()
    if not content:
        return Counter()
    return Counter(json.loads(content))

def save_vocabulary(vocabulary: Counter):
    with VOCABULARY_FILE.open("w") as f:
        json.dump(dict(vocabulary.most_common()), f, indent=2, ensure_ascii=False)

def load_blacklist() -> set[str]:
    if not BLACKLIST_FILE.exists():
        return set()
    with BLACKLIST_FILE.open() as f:
        return {line.strip().lower() for line in f if line.strip()}

def update_vocabulary(vocabulary: Counter, description: str) -> Counter:
    for keyword in description.split(","):
        keyword = keyword.strip().lower()
        if keyword:
            vocabulary[keyword] += 1
    return vocabulary

def build_prompt(vocabulary: Counter, blacklist: set[str], prompt_size: int, event: str | None = None, gps: tuple[float, float] | None = None) -> str:
    base = """\
Describe this photo. Do not guess or extrapolate. Use in exactly this format, with no preamble:
Title: <one short descriptive sentence, max 10 words>
Caption: <one or two sentences describing the scene, people, and mood. Main subject, action or event, setting, mood or lighting, notable details>
Keywords: <15-20 keywords or short phrases, comma-separated. Only terms you see, do not extrapolate>
Rating: <1-5 integer: 5=excellent composition/lighting/interest, 3=average, 1=poor/blurry/badly exposed>
For all output, the target audience are adults, using the keywords to enable search from an archive. Use clear, direct, simple language. Avoid euphemisms.
No punctuation in keywords other than commas.

Example:
Title: Family picnic in a sunny garden
Caption: A family enjoys an outdoor picnic on a sunny afternoon, with children playing around a wooden table.
Keywords: family gathering, outdoor garden, sunny afternoon, children playing, picnic table
Rating: 4"""

    top_terms = [
        term for term, _ in vocabulary.most_common(prompt_size)
        if term not in blacklist
    ]
    if not top_terms and not blacklist and not event and not gps:
        return base

    parts = [base]
    if gps:
        lat, lon = gps
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        parts.append(
            f"GPS coordinates for this photo: {abs(lat):.6f}°{lat_dir}, {abs(lon):.6f}°{lon_dir}. "
            f"You may use the location as a hint for keywords only — do not include coordinates in the Title or Caption."
        )
    if event:
        parts.append(
            f"The folder containing this photo is named '{event}'. "
            f"You may use this as a hint for keywords only — do not use it in the Title. "
            f"Only include keywords from it that genuinely match what you can see in the image."
        )
    if top_terms:
        parts.append(
            f"For consistency, use these terms instead of synonyms where they "
            f"genuinely apply to THIS photo. Do not include any that don't fit: "
            f"{', '.join(top_terms)}"
        )
    if blacklist:
        parts.append(f"Never use these terms: {', '.join(sorted(blacklist))}")
    return "\n\n".join(parts)
