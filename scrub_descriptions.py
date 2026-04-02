import json
from pathlib import Path
from vocabulary import load_blacklist

OUTPUT_FILE = Path(r"D:\Users\tomha\Projects\PhotoArchiving\descriptions.jsonl")

def scrub_keywords(description: str, blacklist: set[str]) -> str:
    # remove blacklisted terms and tidy up any resulting empty slots
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
            original = record["description"]
            scrubbed = scrub_keywords(original, blacklist)
            if scrubbed != original:
                record["description"] = scrubbed
                scrubbed_count += 1
            records.append(record)

    # write back atomically via a temp file to avoid corruption if interrupted
    temp_file = OUTPUT_FILE.with_suffix(".jsonl.tmp")
    with temp_file.open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    temp_file.replace(OUTPUT_FILE)

    print(f"Scrubbed {scrubbed_count} descriptions, {len(records)} total records")

if __name__ == "__main__":
    scrub_descriptions()