from pathlib import Path

# Directory containing your photos (scanned recursively)
PHOTO_DIR = Path(r"")

# Directory where output files are stored:
# descriptions.jsonl, metrics.jsonl, vocabulary.json, blacklist.txt
OUTPUT_DIR = Path(r"")

# Ollama vision model to use
MODEL = "qwen2.5vl:7b"

# File extensions to include when scanning PHOTO_DIR
EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".raf"}

# Number of vocabulary terms to include in the AI prompt.
# Keep this low — smaller models treat long lists as things to copy, not hints.
VOCABULARY_PROMPT_SIZE = 20
