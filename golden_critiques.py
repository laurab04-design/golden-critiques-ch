import os
import json
import re
import urllib.parse
from playwright.async_api import async_playwright
from drive_utils import upload_to_drive

BREED = "RETRIEVER GOLDEN"
RESULTS_FILE = "golden_critiques.json"
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

async def save_progress(results):
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    upload_to_drive(RESULTS_FILE, "application/json")
    print(f"Progress saved: {len(results)} entries")

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password}
        )
        page = await context.new_page()

        # Load existing results to avoid duplicates
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            seen = set((e["show"], e["year"], e["class"]) for e in existing)
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
                await page.wait_for_selector('a[href*="showsextra.php"]', timeout=60000)
                links = await page.locator('a[href*="showsextra.php"]').all()
            except Exception as e:
                print(f"Failed to find show links on {url}: {e}")
                continue

            for link in links:
                href = await link.get_attribute("href")
                if not href or href in seen_links:
                    continue
                seen_links.add(href)
                full_url = urllib.parse.urljoin(BASE_URL + '/', href)
                print(f"Scraping {full_url}")
                await page.goto(full_url)
                text = await page.text_content("body")

                # Show name extraction
                show_match = re.search(r"SHOW NAME:\s*(.*?)\s*\n", text)
                if show_match:
                    show = show_match.group(1).strip()
                else:
                    show = extract_showname_from_url(full_url)

                # Judge extraction
                judge_match = re.search(
                    r"\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\.\s*\n\nPlease note", text, re.DOTALL
                )
                if not judge_match:
                    judge_match = re.search(
                        r"\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\.\s*$",
                        text.strip()
                    )
                judge = judge_match.group(1).strip() if judge_match else "Unknown"

                year_match = re.search(r"(20\d{2})", show)
                year = int(year_match.group(1)) if year_match else "Unknown"

                classes = re.findall(
                    r"\n([A-Z]{2,4})\s*\((\d+),\s*(\d+)\)\s*(.*?)\n(?=[A-Z]{2,4}|\Z)",
                    text,
                    re.DOTALL
                )
                for class_code, entries, absents, block in classes:
                    placements = re.findall(
                        r"(\d)\s+([A-Za-z’'`&.\s]+)’s\s+(.*?)\.(.*?)?(?=\n\d|\n[A-Z]{2,4}|\Z)",
                        block,
                        re.DOTALL
                    )
                    entry = {
                        "show": show,
                        "year": year,
                        "judge": judge,
                        "class": class_code.strip(),
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

                    # Skip duplicates for each class entry
                    if (entry["show"], entry["year"], entry["class"]) not in seen:
                        results.append(entry)
                        seen.add((entry["show"], entry["year"], entry["class"]))

                # Save progress after each show scraped
                await save_progress(results)

        await browser.close()
        print("Scraping complete.")
