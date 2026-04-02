import exiftool
from datetime import datetime
from pathlib import Path
from config import PHOTO_DIR, EXTENSIONS

EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"

# Tags to write when date taken is missing
DATE_TAGS = ["EXIF:DateTimeOriginal", "EXIF:CreateDate", "XMP:DateCreated"]


def filesystem_date(path: Path) -> datetime:
    stat = path.stat()
    # On Windows st_ctime is file creation time; st_mtime is last modified.
    # Take the oldest of the two — modified usually preserves the original
    # camera/scan date even after the file has been copied to a new machine.
    candidates = [datetime.fromtimestamp(stat.st_mtime)]
    if stat.st_ctime:
        candidates.append(datetime.fromtimestamp(stat.st_ctime))
    return min(candidates)


def fix_dates(dry_run: bool = True):
    photos = [p for p in PHOTO_DIR.rglob("*") if p.suffix.lower() in EXTENSIONS]
    print(f"Found {len(photos)} photos")

    fixed = skipped = errors = 0

    with exiftool.ExifToolHelper() as et:
        for photo in photos:
            try:
                tags = et.get_tags(str(photo), ["EXIF:DateTimeOriginal"])[0]
                if tags.get("EXIF:DateTimeOriginal"):
                    skipped += 1
                    continue

                date = filesystem_date(photo)
                date_str = date.strftime(EXIF_DATE_FORMAT)

                if dry_run:
                    print(f"DRY RUN {photo.name}: would set date to {date_str}")
                else:
                    et.set_tags(str(photo), {tag: date_str for tag in DATE_TAGS})
                    print(f"FIXED {photo.name}: {date_str}")

                fixed += 1

            except Exception as e:
                print(f"ERROR {photo.name}: {e}")
                errors += 1

    print(f"\nDone: {fixed} fixed, {skipped} already had date, {errors} errors")


if __name__ == "__main__":
    # run with dry_run=True first to sanity check, then flip to False
    fix_dates(dry_run=True)
