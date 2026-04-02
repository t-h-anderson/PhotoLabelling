import json
from pathlib import Path
from collections import Counter

VOCABULARY_FILE = Path(r"D:\Users\tomha\Projects\PhotoArchiving\vocabulary.json")
BLACKLIST_FILE = Path(r"D:\Users\tomha\Projects\PhotoArchiving\blacklist.txt")

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

def build_prompt(vocabulary: Counter, blacklist: set[str], prompt_size: int) -> str:
    base = """\
Summarise this photo in 10-15 keywords or short phrases, comma-separated.
Cover: main subject, action or event, setting, mood or lighting, notable details.
No sentences, no preamble, no punctuation other than commas.
Example: family gathering, outdoor garden, sunny afternoon, children playing, picnic table"""

    top_terms = [
        term for term, _ in vocabulary.most_common(prompt_size)
        if term not in blacklist
    ]
    if not top_terms and not blacklist:
        return base

    parts = [base]
    if top_terms:
        parts.append(f"Prefer reusing these existing terms where accurate: {', '.join(top_terms)}")
    if blacklist:
        parts.append(f"Never use these terms: {', '.join(sorted(blacklist))}")
    return "\n\n".join(parts)