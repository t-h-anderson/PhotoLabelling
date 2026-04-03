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
CAPTION_TAGS = ["IPTC:Caption-Abstract", "XMP:Caption"]
RATING_TAG = "XMP:Rating"

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

def _filter_existing(existing: dict, desired: dict) -> tuple[dict, list[str]]:
    """Return (tags_to_write, skipped_tags) using a pre-fetched tag snapshot.

    Tags that already have a non-empty value are skipped so we never
    overwrite human-edited metadata. Provenance tags are added separately
    (after this call) and always written.
    """
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
                    # Full pre-write snapshot — used for both the date check,
                    # _filter_existing, and the integrity baseline. One call
                    # instead of three.
                    before_tags = et.get_metadata(target)[0]
                    before_pixels = hash_pixels(target)

                    date_str = (
                        None if before_tags.get("EXIF:DateTimeOriginal")
                        else filesystem_date(target_path).strftime(EXIF_DATE_FORMAT)
                    )

                    desired = _desired_tags(title, caption, keywords, rating, date_str)
                    to_write, skipped = _filter_existing(before_tags, desired)

                    # Provenance tags are always written (overwrite previous runs)
                    to_write["XMP:CreatorTool"] = f"PhotoLabelling/{MODEL}"
                    if labelled_at := record.get("labelled_at"):
                        to_write["XMP:MetadataDate"] = labelled_at
                    if folder_context := record.get("folder_context"):
                        to_write["XMP-iptcExt:Event"] = folder_context

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
                        et.set_tags(target, to_write)  # exiftool auto-creates backup
                        after_pixels = hash_pixels(target)
                        after_tags = et.get_metadata(target)[0]

                        ok, reason = verify_write(
                            before_tags, after_tags,
                            before_pixels, after_pixels,
                            written_tags=set(to_write.keys()),
                        )
                        if ok:
                            bp = backup_path(target)
                            if bp.exists():
                                bp.unlink()
                            print(f"OK: {target_path.name}" + (f" (date backfilled: {date_str})" if date_str else ""))
                        else:
                            print(f"WARNING: {target_path.name}")
                            print(f"  Integrity check failed: {reason}")
                            print(f"  Backup preserved: {backup_path(target).name}")
                    else:
                        print(f"OK: {target_path.name} (nothing to write)")

                except Exception as e:
                    print(f"FAILED {target_path.name}: {e}")

if __name__ == "__main__":
    records = load_descriptions()
    print(f"Loaded {len(records)} records")

    # run with dry_run=True first to sanity check output,
    # then flip to False when happy
    write_tags(records, dry_run=True)
