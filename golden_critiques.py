import os
import json
import re
import urllib.parse
from playwright.async_api import async_playwright
from drive_utils import upload_to_drive, download_from_drive

BREED = "RETRIEVER GOLDEN"
RESULTS_FILE = "golden_critiques.json"
CLASS_CODES_FILE = "class_codes.json"
BASE_URL = "https://www.ourdogs.co.uk"
username = os.getenv("OURDOGS_USER")
password = os.getenv("OURDOGS_PASS")

YEARLY_URLS = [
    "https://www.ourdogs.co.uk/app1/form24ca.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form23ca.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form22ca.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form21c.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form20c.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form19c.php?query=Retriever+golden",
]

def extract_showname_from_url(url):
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    showname_raw = qs.get("showname", ["Unknown"])[0]
    return showname_raw.replace("*", " ").strip()

def load_class_codes():
    local_path = download_from_drive(CLASS_CODES_FILE)
    with open(local_path, "r", encoding="utf-8") as f:
        return set(json.load(f).keys())

def parse_critiques(text, valid_classes):
    text = text.replace("â€TM", "’").replace("â€“", "-").encode("latin1", errors="ignore").decode("utf-8", errors="ignore")

    issue_match = re.search(r"Issue:(\d{2}/\d{2}/\d{4})", text)
    show_match = re.search(r"Issue:\d{2}/\d{2}/\d{4}\s+([A-Z\s\-']+20\d{2})", text)
    breed_match = re.search(r"\n([A-Z ]*RETRIEVER GOLDEN)", text)

    issue_date = issue_match.group(1) if issue_match else "Unknown"
    show = show_match.group(1).strip() if show_match else "Unknown Show"
    breed = breed_match.group(1).strip() if breed_match else "Unknown Breed"

    results = []

    class_blocks = re.findall(
        r"\n([A-Z]{1,6})\s*\((\d+)[,\.]\s*(\d+)\)\s*(.*?)(?=\n[A-Z]{1,6}\s*\(|\Z)",
        text,
        re.DOTALL
    )

    for class_code, entries, absents, block in class_blocks:
        class_code = class_code.strip()
        if class_code not in valid_classes:
            print(f"Skipping invalid class code: {class_code}")
            continue

        placements = re.findall(
            r"(\d)\s+([A-Za-z’'`&.\s]+)’s\s+([A-Za-z0-9 \-’'`&.]+?),?\s*(.*?)(?=\n\d|\n[A-Z]{1,6}\s*\(|\Z)",
            block,
            re.DOTALL
        )

        entry = {
            "show": show,
            "date": issue_date,
            "breed": breed,
            "class": class_code,
            "entries": int(entries),
            "absent": int(absents),
            "placements": []
        }

        for place, owner, dog, critique in placements:
            entry["placements"].append({
                "place": int(place),
                "owner": owner.strip(),
                "dog": dog.strip(),
                "critique": critique.strip() if int(place) in [1, 2] else ""
            })

        results.append(entry)

    return results

async def save_progress(results):
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    upload_to_drive(RESULTS_FILE, "application/json")
    print(f"Progress saved: {len(results)} entries")

async def run_scraper():
    valid_classes = load_class_codes()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password}
        )
        page = await context.new_page()

        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            seen = set((e["show"], e["date"], e["class"]) for e in existing)
        except FileNotFoundError:
            existing = []
            seen = set()

        results = existing.copy()
        seen_links = set()

        for url in YEARLY_URLS:
            print(f"Processing index page: {url}")
            await page.goto(url)
            await page.wait_for_load_state("networkidle")

            try:
                all_links = await page.locator("a").all()
                links = []
                for link in all_links:
                    href = await link.get_attribute("href")
                    if href and "shows" in href and "showname=" in href:
                        links.append(href)
            except Exception as e:
                print(f"Failed to find show links on {url}: {e}")
                continue

            for index, href in enumerate(links):
                if href in seen_links:
                    continue
                seen_links.add(href)
                full_url = urllib.parse.urljoin(BASE_URL + '/', href)
                print(f"Fetching {full_url}")
                await page.goto(full_url)
                await page.wait_for_load_state("domcontentloaded")

                text = await page.content()
                if not text:
                    print(f"Empty page at {full_url}")
                    continue

                os.makedirs("raw_show_pages", exist_ok=True)
                filename = f"raw_show_pages/{Path(href).stem}_{index + 1}.html"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(text)

                parsed = parse_critiques(text, valid_classes)
                for entry in parsed:
                    key = (entry["show"], entry["date"], entry["class"])
                    if key not in seen:
                        results.append(entry)
                        seen.add(key)

                await save_progress(results)

        await browser.close()
        print("Scraping complete.")
