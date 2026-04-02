import json
import exiftool
from pathlib import Path
from fix_dates import filesystem_date, DATE_TAGS, EXIF_DATE_FORMAT

DESCRIPTIONS_FILE = Path(r"D:\Users\tomha\Projects\PhotoArchiving\descriptions.jsonl")

# write to both IPTC and XMP for maximum compatibility with Immich,
# Lightroom, Windows Explorer etc.
KEYWORD_TAGS = ["IPTC:Keywords", "XMP:Subject"]
TITLE_TAGS = ["XMP:Title", "XMP:Description"]

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
            # support both new format (title + keywords) and old format (description)
            title = record.get("title", "")
            keywords = parse_keywords(record.get("keywords", record.get("description", "")))

            if not keywords:
                print(f"SKIP (no keywords): {path}")
                continue

            # check for missing date taken before any writes alter st_mtime
            existing_tags = et.get_tags(path, ["EXIF:DateTimeOriginal"])[0]
            date_str = None
            if not existing_tags.get("EXIF:DateTimeOriginal"):
                date_str = filesystem_date(Path(path)).strftime(EXIF_DATE_FORMAT)

            if dry_run:
                print(f"DRY RUN {path}")
                print(f"  Title:    {title}")
                print(f"  Keywords: {keywords}")
                if date_str:
                    print(f"  Date:     {date_str} (backfilled from filesystem)")
                continue

            try:
                # exiftool creates a .jpg_original backup by default,
                # so your originals are safe
                params = {tag: keywords for tag in KEYWORD_TAGS}
                if title:
                    for tag in TITLE_TAGS:
                        params[tag] = title
                if date_str:
                    for tag in DATE_TAGS:
                        params[tag] = date_str
                et.set_tags(path, params)
                print(f"OK: {Path(path).name}" + (f" (date backfilled: {date_str})" if date_str else ""))
            except Exception as e:
                print(f"FAILED {path}: {e}")

if __name__ == "__main__":
    records = load_descriptions()
    print(f"Loaded {len(records)} records")

    # run with dry_run=True first to sanity check output,
    # then flip to False when happy
    write_tags(records, dry_run=True)