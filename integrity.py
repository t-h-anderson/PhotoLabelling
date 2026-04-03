import hashlib
from pathlib import Path

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# Tags that exiftool may update automatically as a side-effect of any write,
# regardless of what we explicitly set. Changes to these are not unexpected.
EXIFTOOL_AUTO_TAGS = frozenset({
    # Filesystem timestamps
    "File:FileModifyDate",
    "File:FileAccessDate",
    "File:FileSize",
    "File:FilePermissions",
    # Windows "Mark of the Web" ADS — exiftool strips it when rewriting the file
    "File:ZoneIdentifier",
    # Byte order exiftool writes when creating an EXIF IFD from scratch
    "File:ExifByteOrder",
    # IPTC checksum exiftool recomputes whenever IPTC data changes
    "File:CurrentIPTCDigest",
    # XMP toolkit version stamp exiftool writes when it touches XMP
    "XMP:XMPToolkit",
    # MPF (Multi-Picture Format) byte offsets shift when the metadata block grows
    "MPF:MPImageStart",
    "MPF:MPImageLength",
    # IPTC record version/encoding exiftool may auto-set
    "IPTC:ApplicationRecordVersion",
    "IPTC:CodedCharacterSet",
    # IPTC envelope version added when exiftool first writes IPTC to a file
    "IPTC:EnvelopeRecordVersion",
    # Warning exiftool emits when IPTC and XMP are out of sync in the source file
    "ExifTool:Warning",
    "ExifTool:ExifToolVersion",
    # Core EXIF fields exiftool initialises when creating an EXIF IFD from scratch
    # (happens on files that had no EXIF block before the first write)
    "EXIF:ExifVersion",
    "EXIF:ColorSpace",
    "EXIF:ComponentsConfiguration",
    "EXIF:YCbCrPositioning",
    # RAF: embedded preview size and raw-data byte offset shift on every write
    "File:PreviewImage",
    "RAF:StripOffsets",
})


def hash_pixels(path: str) -> str | None:
    """
    Return a SHA256 hash of the decoded pixel data, independent of any
    embedded metadata. Returns None if the format is not supported by Pillow
    (e.g. RAW files), in which case pixel integrity cannot be verified.
    """
    if not _PIL_AVAILABLE:
        return None
    try:
        with Image.open(path) as img:
            return hashlib.sha256(img.tobytes()).hexdigest()
    except Exception:
        return None


def verify_write(
    before_tags: dict,
    after_tags: dict,
    before_pixels: str | None,
    after_pixels: str | None,
    written_tags: set[str],
) -> tuple[bool, str]:
    """
    Verify that an exiftool write only changed what was intended.

    Returns (ok, reason):
      ok=True  – pixel data is intact and only expected tags changed.
      ok=False – unexpected changes detected; the backup should be kept.

    written_tags: the set of tag names passed to et.set_tags() for this write.
    """
    # Pixel integrity: skip if format is unsupported by Pillow
    if before_pixels is not None and after_pixels is not None:
        if before_pixels != after_pixels:
            return False, "pixel data changed unexpectedly after EXIF write"

    # Metadata diff: identify changed tags
    all_keys = set(before_tags) | set(after_tags)
    allowed = written_tags | EXIFTOOL_AUTO_TAGS
    # Allow matching by bare tag name as well as group-qualified name
    # so "IPTC:Keywords" in allowed also covers a key reported as "Keywords"
    allowed_bare = {k.split(":")[-1] for k in allowed}

    unexpected = []
    for key in sorted(all_keys):
        if before_tags.get(key) == after_tags.get(key):
            continue  # unchanged
        bare = key.split(":")[-1]
        if key in allowed or bare in allowed_bare:
            continue  # expected change
        unexpected.append(f"{key}: {before_tags.get(key)!r} → {after_tags.get(key)!r}")

    if unexpected:
        return False, "unexpected metadata changes: " + "; ".join(unexpected)

    return True, ""


def backup_path(path: str) -> Path:
    """
    Return the path where exiftool stores its automatic backup.
    e.g. /photos/img.jpg → /photos/img.jpg_original
    """
    p = Path(path)
    return p.with_suffix(p.suffix + "_original")
