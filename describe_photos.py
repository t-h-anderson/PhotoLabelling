import ollama
import json
import time

from pathlib import Path
from vocabulary import (
    load_vocabulary, save_vocabulary, load_blacklist,
    update_vocabulary, build_prompt
)

PHOTO_DIR = Path(r"S:\ExternalBackup\Tom\Photos\Sorted")
OUTPUT_FILE = Path(r"D:\Users\tomha\Projects\PhotoArchiving\descriptions.jsonl")
METRICS_FILE = Path(r"D:\Users\tomha\Projects\PhotoArchiving\metrics.jsonl")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".raf"}
MODEL = "qwen2.5vl:7b"
VOCABULARY_PROMPT_SIZE = 100

def load_processed() -> set[str]:
    if not OUTPUT_FILE.exists():
        return set()
    with OUTPUT_FILE.open() as f:
        return {json.loads(line)["path"] for line in f if line.strip()}

def describe_photo(image_path: Path, prompt: str) -> tuple[str, dict]:
    wall_start = time.perf_counter()
    response = ollama.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": prompt,
            "images": [str(image_path)],
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

def run_pipeline():
    processed = load_processed()
    photos = [
        p for p in PHOTO_DIR.rglob("*")
        if p.suffix.lower() in EXTENSIONS and str(p) not in processed
    ]
    print(f"Found {len(photos)} unprocessed photos")

    with OUTPUT_FILE.open("a") as out, METRICS_FILE.open("a") as metrics_out:
        for i, photo in enumerate(photos):
            vocabulary = load_vocabulary()
            blacklist = load_blacklist()
            prompt = build_prompt(vocabulary, blacklist, VOCABULARY_PROMPT_SIZE)
            try:

		print(f"[{i+1}/{len(photos)}] Processing {photo.name}...", end="\r")
		raw_description, metrics = describe_photo(photo, prompt)
		description = scrub_keywords(raw_description, blacklist)

                raw_description, metrics = describe_photo(photo, prompt)
                description = scrub_keywords(raw_description, blacklist)

                record = {"path": str(photo), "description": description}
                out.write(json.dumps(record) + "\n")
                out.flush()

                metrics["path"] = str(photo)
                metrics_out.write(json.dumps(metrics) + "\n")
                metrics_out.flush()

                vocabulary = update_vocabulary(vocabulary, description)
                save_vocabulary(vocabulary)

                print(
                    f"[{i+1}/{len(photos)}] "
                    f"vocab={len(vocabulary)} blacklist={len(blacklist)} "
                    f"{metrics['tokens_per_second']}tok/s "
                    f"{photo.name}: {description}"
                )
            except Exception as e:
                print(f"[{i+1}/{len(photos)}] FAILED {photo.name}: {e}")

if __name__ == "__main__":
    run_pipeline()