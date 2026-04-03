import ollama
import json
import time
import io
from datetime import datetime
from PIL import Image, ImageFilter, ImageStat

_client = ollama.Client(timeout=240)

from pathlib import Path
from config import OUTPUT_DIR, MODEL, VOCABULARY_PROMPT_SIZE, MAX_IMAGE_PX, SHARPNESS_BLUR_THRESHOLD, NUM_CTX
from vocabulary import (
    load_vocabulary, save_vocabulary, load_blacklist,
    update_vocabulary, build_prompt, scan_photos, event_from_path
)
from scrub_descriptions import scrub_keywords

OUTPUT_FILE = OUTPUT_DIR / "descriptions.jsonl"
METRICS_FILE = OUTPUT_DIR / "metrics.jsonl"

def load_processed() -> set[str]:
    if not OUTPUT_FILE.exists():
        return set()
    with OUTPUT_FILE.open() as f:
        return {json.loads(line)["path"] for line in f if line.strip()}

def _prepare_image(image_path: Path) -> tuple[bytes, float]:
    with Image.open(image_path) as img:
        img.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX), Image.LANCZOS)
        gray = img.convert("L")
        edge_var = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).var[0]
        rms_contrast = ImageStat.Stat(gray).stddev[0]
        sharpness = round(edge_var / (rms_contrast + 1), 3)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue(), sharpness

def describe_photo(image_path: Path, prompt: str) -> tuple[str, dict]:
    image_bytes, sharpness = _prepare_image(image_path)
    wall_start = time.perf_counter()
    response = _client.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional photo archivist cataloguing a private photo library. "
                    "Describe all photos objectively and factually. "
                    "Never refuse or truncate output — always provide Title, Caption, Keywords, and Rating."
                ),
            },
            {
                "role": "user",
                "content": prompt,
                "images": [image_bytes],
            },
        ],
        options={"num_ctx": NUM_CTX},
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
        "sharpness": sharpness,
    }
    return response["message"]["content"].strip(), metrics

def parse_response(raw: str) -> tuple[str, str, str, int]:
    title = ""
    caption = ""
    keywords = ""
    model_rating = 0
    for line in raw.splitlines():
        low = line.lower()
        if low.startswith("title:"):
            title = line[6:].strip()
        elif low.startswith("caption:"):
            caption = line[8:].strip()
        elif low.startswith("keywords:"):
            keywords = line[9:].strip()
        elif low.startswith("rating:"):
            try:
                model_rating = max(1, min(5, int(line[7:].strip())))
            except ValueError:
                model_rating = 0
    return title, caption, keywords, model_rating

def _sharpness_tier(sharpness: float) -> tuple[int, str]:
    """Returns (max_stars, focus_keyword) for a given sharpness score."""
    t = SHARPNESS_BLUR_THRESHOLD
    if sharpness < t * 0.5:
        return 2, "very blurred focus"
    if sharpness < t:
        return 3, "blurred focus"
    if sharpness < t * 2:
        return 4, "in focus"
    return 5, "sharp focus"

def final_rating(model_rating: int, sharpness: float) -> int:
    max_stars, _ = _sharpness_tier(sharpness)
    return min(model_rating, max_stars) if model_rating else 0

def run_pipeline():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    processed = load_processed()
    photos = [p for p in scan_photos() if p.as_posix() not in processed]
    print(f"Found {len(photos)} unprocessed photos")

    vocabulary = load_vocabulary()
    blacklist = load_blacklist()

    with OUTPUT_FILE.open("a") as out, METRICS_FILE.open("a") as metrics_out:
        for i, photo in enumerate(photos):
            event = event_from_path(photo)
            prompt = build_prompt(vocabulary, blacklist, VOCABULARY_PROMPT_SIZE, event=event)
            try:
                print(f"[{i+1}/{len(photos)}] Processing {photo.name}...", end="\r")
                raw_description, metrics = describe_photo(photo, prompt)
                title, caption, keywords, model_rating = parse_response(raw_description)
                keywords = scrub_keywords(keywords, blacklist)
                rating = final_rating(model_rating, metrics["sharpness"])
                _, focus_tag = _sharpness_tier(metrics["sharpness"])
                keywords = f"{keywords}, {focus_tag}" if keywords else focus_tag

                record = {
                    "path": photo.as_posix(),
                    "title": title,
                    "caption": caption,
                    "keywords": keywords,
                    "rating": rating,
                    "labelled_at": datetime.now().isoformat(timespec="seconds"),
                    "folder_context": event,
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()

                metrics["path"] = photo.as_posix()
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
