import json
import exiftool
from pathlib import Path
from config import OUTPUT_DIR, MODEL
from fix_dates import filesystem_date, DATE_TAGS, EXIF_DATE_FORMAT
from integrity import hash_pixels, verify_write, backup_path

DESCRIPTIONS_FILE = OUTPUT_DIR / "descriptions.jsonl"

# write to both IPTC and XMP for maximum compatibility with Immich,
# Lightroom, Windows Explorer etc.
KEYWORD_TAGS = ["IPTC:Keywords", "XMP:Subject"]
TITLE_TAGS = ["XMP:Title", "XMP:Description"]

# Records which AI model generated the metadata and when it was run.
# XMP:CreatorTool  — the tool/model that produced the content
# XMP:MetadataDate — ISO 8601 timestamp from descriptions.jsonl ("labelled_at");
#                    represents when the model ran, not when tags were written
PROVENANCE_TAGS = ["XMP:CreatorTool", "XMP:MetadataDate"]

def load_descriptions() -> list[dict]:
    with DESCRIPTIONS_FILE.open() as f:
        return [json.loads(line) for line in f if line.strip()]

def parse_keywords(description: str) -> list[str]:
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

            # Full pre-write snapshot — covers date check and integrity baseline
            # in a single exiftool call, before any write can alter st_mtime.
            before_tags = et.get_metadata(path)[0]
            date_str = None
            if not before_tags.get("EXIF:DateTimeOriginal"):
                date_str = filesystem_date(Path(path)).strftime(EXIF_DATE_FORMAT)

            if dry_run:
                print(f"DRY RUN {path}")
                print(f"  Title:    {title}")
                print(f"  Keywords: {keywords}")
                if date_str:
                    print(f"  Date:     {date_str} (backfilled from filesystem)")
                print(f"  Model:    PhotoLabelling/{MODEL}")
                if labelled_at := record.get("labelled_at"):
                    print(f"  Labelled: {labelled_at}")
                continue

            try:
                params = {tag: keywords for tag in KEYWORD_TAGS}
                if title:
                    for tag in TITLE_TAGS:
                        params[tag] = title
                if date_str:
                    for tag in DATE_TAGS:
                        params[tag] = date_str
                params["XMP:CreatorTool"] = f"PhotoLabelling/{MODEL}"
                if labelled_at := record.get("labelled_at"):
                    params["XMP:MetadataDate"] = labelled_at

                before_pixels = hash_pixels(path)
                et.set_tags(path, params)  # exiftool auto-creates .jpg_original backup
                after_pixels = hash_pixels(path)
                after_tags = et.get_metadata(path)[0]

                ok, reason = verify_write(
                    before_tags, after_tags,
                    before_pixels, after_pixels,
                    written_tags=set(params.keys()),
                )

                suffix = f" (date backfilled: {date_str})" if date_str else ""
                if ok:
                    bp = backup_path(path)
                    if bp.exists():
                        bp.unlink()
                    print(f"OK: {Path(path).name}{suffix}")
                else:
                    print(f"WARNING: {Path(path).name}{suffix}")
                    print(f"  Integrity check failed: {reason}")
                    print(f"  Backup preserved: {backup_path(path).name}")
            except Exception as e:
                print(f"FAILED {path}: {e}")

if __name__ == "__main__":
    records = load_descriptions()
    print(f"Loaded {len(records)} records")

    # run with dry_run=True first to sanity check output,
    # then flip to False when happy
    write_tags(records, dry_run=True)