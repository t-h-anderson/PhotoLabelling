from pathlib import Path

# Directory containing your photos (scanned recursively)
PHOTO_DIR = Path(r"")

# Directory where output files are stored:
# descriptions.jsonl, metrics.jsonl, vocabulary.json, blacklist.txt
OUTPUT_DIR = Path(r"")

# Ollama vision model to use
MODEL = "qwen2.5vl:7b"

# File extensions to include when scanning PHOTO_DIR.
# RAF (Fujifilm RAW) is excluded — the paired JPEG is processed instead,
# and tags are mirrored to the RAF by descriptions.py.
EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".tiff"}

# Images are resized to this pixel limit on the long edge before being sent to
# the model. Keeps large HDR/RAW-derived JPEGs from exhausting VRAM.
MAX_IMAGE_PX = 1920

# Laplacian variance below this value is considered blurry and reduces the
# model's rating by 1. Run a batch and check metrics.jsonl sharpness values
# to calibrate this for your photos.
SHARPNESS_BLUR_THRESHOLD = 100

# Number of vocabulary terms to include in the AI prompt.
# Keep this low — smaller models treat long lists as things to copy, not hints.
VOCABULARY_PROMPT_SIZE = 20
