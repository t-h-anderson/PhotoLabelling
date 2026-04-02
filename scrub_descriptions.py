import json
from pathlib import Path
from config import OUTPUT_DIR
from vocabulary import load_blacklist

OUTPUT_FILE = OUTPUT_DIR / "descriptions.jsonl"

def scrub_keywords(description: str, blacklist: set[str]) -> str:
    keywords = [
        k.strip() for k in description.split(",")
        if k.strip().lower() not in blacklist
    ]
    return ", ".join(keywords)

def scrub_descriptions():
    blacklist = load_blacklist()
    if not blacklist:
        print("Blacklist is empty, nothing to do")
        return

    records = []
    scrubbed_count = 0

    with OUTPUT_FILE.open() as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            field = "keywords" if "keywords" in record else "description"
            original = record[field]
            scrubbed = scrub_keywords(original, blacklist)
            if scrubbed != original:
                record[field] = scrubbed
                scrubbed_count += 1
            records.append(record)

    # write back atomically via a temp file to avoid corruption if interrupted
    temp_file = OUTPUT_FILE.with_suffix(".jsonl.tmp")
    with temp_file.open("w") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp_file.replace(OUTPUT_FILE)

    print(f"Scrubbed {scrubbed_count} descriptions, {len(records)} total records")

if __name__ == "__main__":
    scrub_descriptions()