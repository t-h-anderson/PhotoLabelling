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
CAPTION_TAGS = ["IPTC:Caption-Abstract", "XMP:Caption"]
RATING_TAG = "XMP:Rating"

def load_descriptions() -> list[dict]:
    with DESCRIPTIONS_FILE.open() as f:
        return [json.loads(line) for line in f if line.strip()]

def parse_keywords(description: str) -> list[str]:
    return [k.strip() for k in description.split(",") if k.strip()]

def paired_raf(jpeg_path: Path) -> Path | None:
    raf = jpeg_path.with_suffix(".RAF")
    return raf if raf.exists() else None

def _desired_tags(title: str, caption: str, keywords: list[str], rating: int, date_str: str | None) -> dict:
    params = {tag: keywords for tag in KEYWORD_TAGS}
    if title:
        for tag in TITLE_TAGS:
            params[tag] = title
    if caption:
        for tag in CAPTION_TAGS:
            params[tag] = caption
    if rating:
        params[RATING_TAG] = rating
    if date_str:
        for tag in DATE_TAGS:
            params[tag] = date_str
    return params

def _filter_existing(et, target: str, desired: dict) -> tuple[dict, list[str]]:
    """Return (tags_to_write, skipped_tags) after reading existing values."""
    existing = et.get_tags(target, list(desired.keys()))[0]
    to_write, skipped = {}, []
    for tag, value in desired.items():
        ev = existing.get(tag)
        # treat empty string, empty list, and 0 rating as unset
        if ev and ev != 0:
            skipped.append(tag)
        else:
            to_write[tag] = value
    return to_write, skipped

def write_tags(records: list[dict], dry_run: bool = True):
    with exiftool.ExifToolHelper() as et:
        for record in records:
            path = record["path"]
            # support both new format (title + keywords) and old format (description)
            title = record.get("title", "")
            caption = record.get("caption", "")
            keywords = parse_keywords(record.get("keywords", record.get("description", "")))
            rating = record.get("rating", 0)

            if not keywords:
                print(f"SKIP (no keywords): {path}")
                continue

            raf = paired_raf(Path(path))
            targets = [path, str(raf)] if raf else [path]

            for target in targets:
                target_path = Path(target)
                try:
                    # read existing date before any write could alter st_mtime
                    date_existing = et.get_tags(target, ["EXIF:DateTimeOriginal"])[0]
                    date_str = (
                        None if date_existing.get("EXIF:DateTimeOriginal")
                        else filesystem_date(target_path).strftime(EXIF_DATE_FORMAT)
                    )

                    desired = _desired_tags(title, caption, keywords, rating, date_str)
                    to_write, skipped = _filter_existing(et, target, desired)

                    if dry_run:
                        print(f"DRY RUN {target_path.name}")
                        for tag, value in to_write.items():
                            print(f"  SET  {tag}: {value}")
                        for tag in skipped:
                            print(f"  WARN {tag}: already populated, skipping")
                        continue

                    if skipped:
                        print(f"WARN {target_path.name}: skipped {len(skipped)} existing field(s): {', '.join(skipped)}")

                    if to_write:
                        # exiftool creates a .jpg_original / .RAF_original backup by default
                        et.set_tags(target, to_write)
                    print(f"OK: {target_path.name}" + (f" (date backfilled: {date_str})" if date_str else ""))

                except Exception as e:
                    print(f"FAILED {target_path.name}: {e}")

if __name__ == "__main__":
    records = load_descriptions()
    print(f"Loaded {len(records)} records")

    # run with dry_run=True first to sanity check output,
    # then flip to False when happy
    write_tags(records, dry_run=True)