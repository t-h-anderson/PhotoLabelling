import json
import re
from pathlib import Path
from collections import Counter
from config import OUTPUT_DIR, PHOTO_DIR, EXTENSIONS

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
        json.dump(dict(vocabulary.most_common()), f, indent=2)

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

def build_prompt(vocabulary: Counter, blacklist: set[str], prompt_size: int, event: str | None = None) -> str:
    base = """\
Describe this photo in exactly this format, with no preamble:
Title: <one short descriptive sentence, max 10 words>
Caption: <Detailed description of the scene, people in detail, and mood.>
Keywords: <15-20 keywords or short phrases, comma-separated>

The keywords should cover: main subject, action or event, setting, mood or lighting, notable details. 
Audience are adult. Keywords to enable search from an archive. Use clear, direct, simple language. Avoid euphemisms.
No punctuation in keywords other than commas.
Example:
Title: Family picnic in a sunny garden
Keywords: family gathering, outdoor garden, sunny afternoon, children playing, picnic table"""

    top_terms = [
        term for term, _ in vocabulary.most_common(prompt_size)
        if term not in blacklist
    ]
    if not top_terms and not blacklist and not event:
        return base

    parts = [base]
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