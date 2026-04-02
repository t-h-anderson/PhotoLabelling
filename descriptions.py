import json
import exiftool
from pathlib import Path
from config import OUTPUT_DIR
from fix_dates import filesystem_date, DATE_TAGS, EXIF_DATE_FORMAT

DESCRIPTIONS_FILE = OUTPUT_DIR / "descriptions.jsonl"

# write to both IPTC and XMP for maximum compatibility with Immich,
# Lightroom, Windows Explorer etc.
KEYWORD_TAGS = ["IPTC:Keywords", "XMP:Subject"]
TITLE_TAGS = ["XMP:Title", "XMP:Description"]

def load_descriptions() -> list[dict]:
    with DESCRIPTIONS_FILE.open() as f:
        return [json.loads(line) for line in f if line.strip()]

def parse_keywords(description: str) -> list[str]:
    return [k.strip() for k in description.split(",") if k.strip()]

def paired_raf(jpeg_path: Path) -> Path | None:
    raf = jpeg_path.with_suffix(".RAF")
    return raf if raf.exists() else None

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

            raf = paired_raf(Path(path))

            if dry_run:
                print(f"DRY RUN {path}")
                print(f"  Title:    {title}")
                print(f"  Keywords: {keywords}")
                if date_str:
                    print(f"  Date:     {date_str} (backfilled from filesystem)")
                if raf:
                    print(f"  RAF:      {raf.name} (tags will be mirrored)")
                continue

            params = {tag: keywords for tag in KEYWORD_TAGS}
            if title:
                for tag in TITLE_TAGS:
                    params[tag] = title
            if date_str:
                for tag in DATE_TAGS:
                    params[tag] = date_str

            targets = [path, str(raf)] if raf else [path]
            for target in targets:
                try:
                    # exiftool creates a .jpg_original / .RAF_original backup by default
                    et.set_tags(target, params)
                    print(f"OK: {Path(target).name}" + (f" (date backfilled: {date_str})" if date_str else ""))
                except Exception as e:
                    print(f"FAILED {Path(target).name}: {e}")

if __name__ == "__main__":
    records = load_descriptions()
    print(f"Loaded {len(records)} records")

    # run with dry_run=True first to sanity check output,
    # then flip to False when happy
    write_tags(records, dry_run=True)