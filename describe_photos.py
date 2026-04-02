import ollama
import json
import time
import io
from PIL import Image

_client = ollama.Client(timeout=120)

from pathlib import Path
from config import OUTPUT_DIR, MODEL, VOCABULARY_PROMPT_SIZE, MAX_IMAGE_PX
from vocabulary import (
    load_vocabulary, save_vocabulary, load_blacklist,
    update_vocabulary, build_prompt, scan_photos
)
from scrub_descriptions import scrub_keywords

OUTPUT_FILE = OUTPUT_DIR / "descriptions.jsonl"
METRICS_FILE = OUTPUT_DIR / "metrics.jsonl"

def load_processed() -> set[str]:
    if not OUTPUT_FILE.exists():
        return set()
    with OUTPUT_FILE.open() as f:
        return {json.loads(line)["path"] for line in f if line.strip()}

def _prepare_image(image_path: Path) -> bytes:
    with Image.open(image_path) as img:
        img.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

def describe_photo(image_path: Path, prompt: str) -> tuple[str, dict]:
    image_bytes = _prepare_image(image_path)
    wall_start = time.perf_counter()
    response = _client.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": prompt,
            "images": [image_bytes],
        }],
    )
    wall_seconds = time.perf_counter() - wall_start

    # ollama reports durations in nanoseconds
    ns = 1e9
    eval_count = response.eval_count or 0
    eval_duration = response.eval_duration or 0
    tokens_per_second = (eval_count / eval_duration * ns) if eval_duration else 0

    metrics = {
        "wall_seconds": round(wall_seconds, 2),
        "tokens_per_second": round(tokens_per_second, 1),
        "output_tokens": eval_count,
        "prompt_tokens": response.prompt_eval_count or 0,
        "load_duration_seconds": round((response.load_duration or 0) / ns, 3),
    }
    return response["message"]["content"].strip(), metrics

def parse_response(raw: str) -> tuple[str, str, str]:
    title = ""
    caption = ""
    keywords = ""
    for line in raw.splitlines():
        low = line.lower()
        if low.startswith("title:"):
            title = line[6:].strip()
        elif low.startswith("caption:"):
            caption = line[8:].strip()
        elif low.startswith("keywords:"):
            keywords = line[9:].strip()
    return title, caption, keywords

def run_pipeline():
    processed = load_processed()
    photos = [p for p in scan_photos() if str(p) not in processed]
    print(f"Found {len(photos)} unprocessed photos")

    vocabulary = load_vocabulary()
    blacklist = load_blacklist()

    with OUTPUT_FILE.open("a") as out, METRICS_FILE.open("a") as metrics_out:
        for i, photo in enumerate(photos):
            prompt = build_prompt(vocabulary, blacklist, VOCABULARY_PROMPT_SIZE)
            try:
                print(f"[{i+1}/{len(photos)}] Processing {photo.name}...", end="\r")
                raw_description, metrics = describe_photo(photo, prompt)
                title, caption, keywords = parse_response(raw_description)
                keywords = scrub_keywords(keywords, blacklist)

                record = {"path": str(photo), "title": title, "caption": caption, "keywords": keywords}
                out.write(json.dumps(record) + "\n")
                out.flush()

                metrics["path"] = str(photo)
                metrics_out.write(json.dumps(metrics) + "\n")
                metrics_out.flush()

                vocabulary = update_vocabulary(vocabulary, keywords)
                save_vocabulary(vocabulary)

                print(
                    f"[{i+1}/{len(photos)}] "
                    f"vocab={len(vocabulary)} blacklist={len(blacklist)} "
                    f"{metrics['tokens_per_second']}tok/s "
                    f"{photo.name}: {title}"
                )
            except Exception as e:
                print(f"[{i+1}/{len(photos)}] FAILED {photo.name}: {e}")

if __name__ == "__main__":
    run_pipeline()