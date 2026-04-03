import exiftool
from datetime import datetime
from pathlib import Path
from vocabulary import scan_photos
from integrity import hash_pixels, verify_write, backup_path

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
    photos = scan_photos()
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
                    params = {tag: date_str for tag in DATE_TAGS}
                    before_tags = et.get_metadata(str(photo))[0]
                    before_pixels = hash_pixels(str(photo))
                    et.set_tags(str(photo), params)  # exiftool auto-creates .jpg_original backup
                    after_pixels = hash_pixels(str(photo))
                    after_tags = et.get_metadata(str(photo))[0]

                    ok, reason = verify_write(
                        before_tags, after_tags,
                        before_pixels, after_pixels,
                        written_tags=set(params.keys()),
                    )
                    if ok:
                        bp = backup_path(str(photo))
                        if bp.exists():
                            bp.unlink()
                        print(f"FIXED {photo.name}: {date_str}")
                    else:
                        print(f"WARNING {photo.name}: {date_str}")
                        print(f"  Integrity check failed: {reason}")
                        print(f"  Backup preserved: {backup_path(str(photo)).name}")

                fixed += 1

            except Exception as e:
                print(f"ERROR {photo.name}: {e}")
                errors += 1

    print(f"\nDone: {fixed} fixed, {skipped} already had date, {errors} errors")


if __name__ == "__main__":
    # run with dry_run=True first to sanity check, then flip to False
    fix_dates(dry_run=True)
