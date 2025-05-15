import os
import json
import re
from playwright.async_api import async_playwright
from drive_utils import upload_to_drive

BREED = "RETRIEVER GOLDEN"
RESULTS_FILE = "golden_critiques.json"
BASE_URL = "https://www.ourdogs.co.uk"
username = os.getenv("OURDOGS_USER")
password = os.getenv("OURDOGS_PASS")

YEARLY_URLS = [
    "https://www.ourdogs.co.uk/app1/formextraca.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form24ca.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form23ca.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form22ca.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form21c.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form20c.php?query=Retriever+golden",
    "https://www.ourdogs.co.uk/app1/form19c.php?query=Retriever+golden",
]

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Login
            await page.goto(f"{BASE_URL}/members/index.php")
            await page.wait_for_selector('form[name="loginform"] input[name="username"]')
            await page.fill('form[name="loginform"] input[name="username"]', username)
            await page.fill('form[name="loginform"] input[name="password"]', password)
            await page.click('form[name="loginform"] input[type="submit"]')
            await page.wait_for_load_state("networkidle")
        except Exception:
            html = await page.content()
            with open("debug_login.html", "w", encoding="utf-8") as f:
                f.write(html)
            await page.screenshot(path="debug_login.png", full_page=True)
            upload_to_drive("debug_login.html", "text/html")
            upload_to_drive("debug_login.png", "image/png")
            print("Login failed. Uploaded debug files.")
            await browser.close()
            return

        seen_links = set()
        results = []

        for url in YEARLY_URLS:
            print(f"Processing index page: {url}")
            await page.goto(url)
            await page.wait_for_load_state("networkidle")

            links = await page.locator('a[href*="showsextra.php"]').all()
            for link in links:
                href = await link.get_attribute("href")
                if not href or href in seen_links:
                    continue
                seen_links.add(href)
                full_url = f"{BASE_URL}/app1/{href}"
                print(f"Scraping {full_url}")
                await page.goto(full_url)
                text = await page.text_content("body")

                show_match = re.search(r"SHOW NAME:\s*(.*?)\s*\n", text)
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
                    results.append(entry)

        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            seen = set((e["show"], e["year"], e["class"]) for e in existing)
        except FileNotFoundError:
            existing = []
            seen = set()

        fresh = [e for e in results if (e["show"], e["year"], e["class"]) not in seen]
        combined = existing + fresh

        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2)

        upload_to_drive(RESULTS_FILE, "application/json")
        await browser.close()
        print("Scraping complete.")
