import os
import re
import json
from ftfy import fix_text
from drive_utils import upload_to_drive

INPUT_FOLDER = "golden-critiques"
OUTPUT_FILE = os.path.join(INPUT_FOLDER, "golden_critiques_by_dog.json")

def extract_year_from_filename(filename):
    match = re.search(r'(\d{4})', filename)
    return int(match.group(1)) if match else None

def extract_critique_text(text):
    text = fix_text(text)
    start = text.find("RETRIEVER GOLDEN")
    end = text.find("Please note that all reports and articles")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start + len("RETRIEVER GOLDEN"):end].strip()

def extract_dog_critiques(critique_text, source_file):
    dog_critiques = {}
    class_blocks = re.split(r'\n?(?=(?:[A-Z]{1,4}|[A-Z]{2,4} \d)[ \n])', critique_text)

    for block in class_blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        class_header = lines[0].strip()
        rest = " ".join(lines[1:]) if len(lines) > 1 else lines[0]
        placements = re.split(r'(?<=\.)\s*(\d(?:st|nd|rd|th)?(?:\s|&|,|$))', rest)

        current_pos = None
        buffer = ""
        for chunk in placements:
            chunk = chunk.strip()
            if re.match(r'^\d(?:st|nd|rd|th)?$', chunk):
                if buffer:
                    match = re.match(r"(.+?)['’]s (.+?)(?:,|\(|\.).", buffer)
                    if match:
                        owner, dog = match.groups()
                        dog = fix_text(dog.strip())
                        dog_critiques.setdefault(dog, []).append({
                            "class": class_header,
                            "critique": buffer.strip(),
                            "source": source_file,
                            "show": source_file.split("_")[0],
                            "year": extract_year_from_filename(source_file)
                        })
                    buffer = ""
                current_pos = chunk
            else:
                buffer += " " + chunk

        if buffer:
            match = re.match(r"(.+?)['’]s (.+?)(?:,|\(|\.).", buffer)
            if match:
                owner, dog = match.groups()
                dog = fix_text(dog.strip())
                dog_critiques.setdefault(dog, []).append({
                    "class": class_header,
                    "critique": buffer.strip(),
                    "source": source_file,
                    "show": source_file.split("_")[0],
                    "year": extract_year_from_filename(source_file)
                })

    return dog_critiques

def process_all_files(input_folder, existing_data=None):
    all_dogs = existing_data or {}

    already_processed_files = set()
    for entries in all_dogs.values():
        for entry in entries:
            if "source" in entry:
                already_processed_files.add(entry["source"])

    for filename in os.listdir(input_folder):
        if not filename.lower().endswith(".txt"):
            continue
        if filename in already_processed_files:
            print(f"[SKIP] Already processed {filename}")
            continue

        filepath = os.path.join(input_folder, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            raw_text = fix_text(f.read())
        extracted = extract_critique_text(raw_text)
        if not extracted:
            print(f"[SKIP] No retrievable block in {filename}")
            continue
        dog_critiques = extract_dog_critiques(extracted, source_file=filename)
        for dog, entries in dog_critiques.items():
            all_dogs.setdefault(dog, []).extend(entries)

    # Deduplicate critiques per dog by exact text
    for dog, entries in all_dogs.items():
        seen_critique_texts = set()
        deduped = []
        for entry in entries:
            text = entry.get("critique", "").strip()
            if text and text not in seen_critique_texts:
                seen_critique_texts.add(text)
                deduped.append(entry)
        deduped.sort(key=lambda e: e.get("year", 0), reverse=True)
        all_dogs[dog] = deduped

    return all_dogs

if __name__ == "__main__":
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
    else:
        existing_data = {}

    data = process_all_files(INPUT_FOLDER, existing_data=existing_data)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Extracted critiques saved to {OUTPUT_FILE}")
    upload_to_drive(OUTPUT_FILE, folder_name="golden-critiques")
