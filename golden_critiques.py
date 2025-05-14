import os
import json
import base64
import re
from playwright.async_api import async_playwright
from drive_utils import upload_to_drive

BREED = "RETRIEVER GOLDEN"
RESULTS_FILE = "golden_critiques.json"
BASE_URL = "https://www.ourdogs.co.uk"

username = os.env("OURDOGS_USER")
password = os.env("OURDOGS_PASS")

async def upload_debug_to_drive(page):
    html = await page.content()
    with open("debug_login.html", "w", encoding="utf-8") as f:
        f.write(html)
    await page.screenshot(path="debug_login.png", full_page=True)
    upload_to_drive("debug_login.html", "text/html")
    upload_to_drive("debug_login.png", "image/png")
    print("Uploaded login debug files.")

async def login_and_scrape(page):
    critiques = []
    await page.goto(f"{BASE_URL}/app1/champshows.php")
    year_links = await page.locator('a:has-text("20")').all()

    for link in year_links:
        href = await link.get_attribute("href")
        if not href:
            continue
        full_url = f"{BASE_URL}/app1/{href}"
        print(f"Visiting year page: {full_url}")
        await page.goto(full_url)
        await page.wait_for_load_state("networkidle")

        breed_links = await page.locator(f'a:has-text("{BREED.upper()}")').all()
        for breed_link in breed_links:
            show_url = await breed_link.get_attribute("href")
            if not show_url:
                continue
            full_show_url = f"{BASE_URL}/app1/{show_url}"
            print(f"Scraping {full_show_url}")
            await page.goto(full_show_url)
            text = await page.text_content("body")

            show_match = re.search(r"Championship Show\s*-\s*(.*?)\s*\n", text)
            judge_match = re.search(r"\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\.\s*$", text.strip())

            show = show_match.group(1).strip() if show_match else "Unknown Show"
            judge = judge_match.group(1).strip() if judge_match else "Unknown"
            year_match = re.search(r"(20\d{2})", show)
            year = int(year_match.group(1)) if year_match else "Unknown"

            classes = re.findall(r"\n([A-Z]{2,4})\s*\((\d+),\s*(\d+)\)\s*(.*?)\n(?=[A-Z]{2,4}|\Z)", text, re.DOTALL)
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
                critiques.append(entry)

    return critiques

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Attempt login
        await page.goto(f"{BASE_URL}/members/index.php")
        try:
            await page.fill('input[name="username"]')
            await page.fill('input[name="password"]')
            await page.click('input[type="submit"]')
            await page.wait_for_load_state("networkidle")
        except Exception:
            print("Login failed or not detected. Dumping HTML and screenshot...")
            await upload_debug_to_drive(page)
            await browser.close()
            return

        new_data = await login_and_scrape(page)

        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            seen = set((entry["show"], entry["year"]) for entry in existing_data)
        except FileNotFoundError:
            existing_data = []
            seen = set()

        fresh = [entry for entry in new_data if (entry["show"], entry["year"]) not in seen]
        combined = existing_data + fresh

        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2)

        await browser.close()
        print("Scraping complete.")
