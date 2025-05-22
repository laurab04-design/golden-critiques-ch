import os
import urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright
from drive_utils import upload_to_drive

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
    return showname_raw.replace("*", " ").strip().replace(" ", "_")

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password}
        )
        page = await context.new_page()

        seen_links = set()
        os.makedirs("raw_show_text", exist_ok=True)

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

            for href in links:
                if href in seen_links:
                    continue
                seen_links.add(href)

                full_url = urllib.parse.urljoin(BASE_URL + "/", href)
                showname = extract_showname_from_url(full_url)
                filename = f"raw_show_text/{showname}.txt"

                print(f"Fetching {full_url}")
                try:
                    await page.goto(full_url)
                    await page.wait_for_load_state("domcontentloaded")
                    text = await page.locator("body").inner_text()
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(text)
                    print(f"Saved text to {filename}")
                    upload_to_drive(filename, "text/plain", "golden-critiques")
                except Exception as e:
                    print(f"Failed to fetch or save {full_url}: {e}")

        await browser.close()
        print("Text scraping complete.")
