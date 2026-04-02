import json
import exiftool
from pathlib import Path

DESCRIPTIONS_FILE = Path(r"D:\Users\tomha\Projects\PhotoArchiving\descriptions.jsonl")

# write to both IPTC and XMP for maximum compatibility with Immich,
# Lightroom, Windows Explorer etc.
KEYWORD_TAGS = ["IPTC:Keywords", "XMP:Subject"]
DESCRIPTION_TAG = "XMP:Description"

def load_descriptions() -> list[dict]:
    with DESCRIPTIONS_FILE.open() as f:
        return [json.loads(line) for line in f if line.strip()]

def parse_keywords(description: str) -> list[str]:
    # strip whitespace from each keyword the model produced
    return [k.strip() for k in description.split(",") if k.strip()]

def write_tags(records: list[dict], dry_run: bool = True):
    with exiftool.ExifToolHelper() as et:
        for record in records:
            path = record["path"]
            keywords = parse_keywords(record["description"])

            if not keywords:
                print(f"SKIP (no keywords): {path}")
                continue

            if dry_run:
                print(f"DRY RUN {path}")
                print(f"  Keywords: {keywords}")
                continue

            try:
                # exiftool creates a .jpg_original backup by default,
                # so your originals are safe
                params = {tag: keywords for tag in KEYWORD_TAGS}
                params[DESCRIPTION_TAG] = record["description"]
                et.set_tags(path, params)
                print(f"OK: {Path(path).name}")
            except Exception as e:
                print(f"FAILED {path}: {e}")

if __name__ == "__main__":
    records = load_descriptions()
    print(f"Loaded {len(records)} records")

    # run with dry_run=True first to sanity check output,
    # then flip to False when happy
    write_tags(records, dry_run=True)