import os
import re
import json
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

OURDOGS_USER = os.getenv("OURDOGS_USER")
OURDOGS_PASS = os.getenv("OURDOGS_PASS")

BREED = "RETRIEVER GOLDEN"
YEARS = list(range(2025, 2011, -1))

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Login
        await page.goto("https://www.ourdogs.co.uk/members/breedindex.php")
        await page.get_by_placeholder("Email").fill(OURDOGS_USER)
        await page.get_by_placeholder("Password").fill(OURDOGS_PASS)
        await page.get_by_role("button", name="Login").click()

        results = []

        for year in YEARS:
            await page.goto("https://www.ourdogs.co.uk/members/breedindex.php")
            await page.get_by_placeholder("Search Breed").fill(BREED)
            await page.keyboard.press("Enter")
            await page.wait_for_selector("text=Championship Show")

            show_links = await page.locator("a:has-text('Championship Show')").all()
            for link in show_links:
                url = await link.get_attribute("href")
                if not url:
                    continue
                show_url = f"https://www.ourdogs.co.uk/members/{url}"
                await page.goto(show_url)
                content = await page.content()
                soup = BeautifulSoup(content, "html.parser")

                text = soup.get_text(separator="\n")
                if "retriever" not in text.lower():
                    continue

                show_name = soup.find("h1").get_text(strip=True) if soup.find("h1") else "Unknown Show"
                date_match = re.search(r"\b(\d{1,2} \w+ \d{4})\b", text)
                show_date = date_match.group(1) if date_match else f"{year}-01-01"
                judge_match = re.search(r"^\s*([A-Z][a-z]+\s+[A-Z][a-z]+)\s*$", text.strip().split("\n")[-1])
                judge = judge_match.group(1) if judge_match else "Unknown Judge"

                class_blocks = re.findall(r"(\b[A-Z]{2,3} ?[A-Z]?(?:\s*\(\d+,\d+\))?.*?)(?=\n[A-Z]{2,3} ?[A-Z]?\s*\(|\Z)", text, re.DOTALL)

                for block in class_blocks:
                    class_header = re.match(r"([A-Z]{2,3} ?[A-Z]?)\s*\((\d+),(\d+)\)", block)
                    if not class_header:
                        continue
                    class_code = class_header.group(1).strip()
                    entries = int(class_header.group(2))
                    absent = int(class_header.group(3))

                    placements = []
                    for place in [1, 2, 3]:
                        pat = rf"{place}\s+([\w&â'`-]+)\s+[â'`]?(.*?)(?=(\n\d\s|\Z))"
                        match = re.search(pat, block, re.DOTALL)
                        if match:
                            owner = match.group(1).strip()
                            dog = match.group(2).strip().split(".")[0].strip()
                            crit = match.group(2).strip().split(".", 1)[1].strip() if place in [1, 2] and "." in match.group(2) else None
                            placements.append({
                                "place": place,
                                "owner": owner,
                                "dog": dog,
                                "critique": crit
                            })

                    results.append({
                        "show": show_name,
                        "date": show_date,
                        "judge": judge,
                        "breed": BREED,
                        "class_code": class_code,
                        "entries": entries,
                        "absent": absent,
                        "placements": placements
                    })

        await browser.close()
        return results
