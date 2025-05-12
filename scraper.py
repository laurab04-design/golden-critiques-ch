# scraper.py

import asyncio
import os
import re
import json
from typing import List, Dict
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

BREED = "RETRIEVER GOLDEN"
BASE_URL = "https://www.ourdogs.co.uk"
SEARCH_URL = f"{BASE_URL}/members/gen-champshows/gen-chshow-index.php"

async def run_scraper():
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(SEARCH_URL)
        await page.fill('input[name="breed"]', BREED)
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle")

        links = await extract_result_links(page)
        for link in links:
            try:
                data = await parse_critique_page(context, link)
                results.extend(data)
            except Exception as e:
                print(f"Failed to parse {link}: {e}")

        await browser.close()

    with open("golden_critiques.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

async def extract_result_links(page) -> List[str]:
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        if "critique" in a.text.lower() and "golden" in a.text.lower():
            href = a["href"]
            full_url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
            links.append(full_url)
    return links

async def parse_critique_page(context, url: str) -> List[Dict]:
    page = await context.new_page()
    await page.goto(url)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    paragraphs = soup.find_all("p")
    entries = []

    current_class = None
    current_entry = {}
    for p in paragraphs:
        text = p.get_text().strip()
        class_header = re.match(r"([A-Z]{1,3}[B|D]?)\s*\((\d+),\s*(\d+)\)", text)
        if class_header:
            current_class = class_header.group(1)
            total = int(class_header.group(2))
            absent = int(class_header.group(3))
            current_entry = {
                "class_code": current_class,
                "entries": total,
                "absent": absent,
                "placings": [],
            }
            entries.append(current_entry)
            continue

        placing_match = re.findall(r"\d\s+[A-Z][a-zA-Z\-’'.& ]+’s\s+[^.]+", text)
        if placing_match and current_entry:
            placings = []
            for match in placing_match:
                place = int(match.strip()[0])
                owner_dog = match.strip()[2:]
                owner, dog = owner_dog.split("’s", 1)
                placings.append({
                    "place": place,
                    "owner": owner.strip(),
                    "dog_name": dog.strip(". ").strip()
                })
            current_entry["placings"].extend(placings)
            current_entry["critique"] = text

    await page.close()
    return entries

if __name__ == "__main__":
    asyncio.run(run_scraper())
