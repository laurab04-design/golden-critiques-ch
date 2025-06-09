import os
import re
import json
from ftfy import fix_text
from golden_judges_scraper import upload_to_drive

INPUT_FOLDER = "golden-critiques"  # Local folder of input .txt files
OUTPUT_FILE = "golden_critiques_by_dog.json"

def extract_critique_text(text):
    text = fix_text(text)
    start = text.find("RETRIEVER GOLDEN")
    end = text.find("Please note that all reports and articles")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start + len("RETRIEVER GOLDEN"):end].strip()

def extract_dog_critiques(critique_text):
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
                            "critique": buffer.strip()
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
                    "critique": buffer.strip()
                })

    return dog_critiques

def process_all_files(input_folder):
    all_dogs = {}
    for filename in os.listdir(input_folder):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(input_folder, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            raw_text = fix_text(f.read())
        extracted = extract_critique_text(raw_text)
        if not extracted:
            continue
        dog_critiques = extract_dog_critiques(extracted)
        for dog, entries in dog_critiques.items():
            all_dogs.setdefault(dog, []).extend(entries)
    return all_dogs

if __name__ == "__main__":
    data = process_all_files(INPUT_FOLDER)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Extracted critiques saved to {OUTPUT_FILE}")
    upload_to_drive(OUTPUT_FILE, folder_id=os.getenv("GDRIVE_FOLDER_ID"))
