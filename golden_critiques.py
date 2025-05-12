import os
import json
import base64
import re
from playwright.async_api import async_playwright
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

BREED = "RETRIEVER GOLDEN"
RESULTS_FILE = "golden_critiques.json"

def upload_to_drive(filename: str, folder_name: str = "golden-critiques"):
    creds_data = os.getenv("GOOGLE_SERVICE_ACCOUNT_BASE64")
    if not creds_data:
        print("No GOOGLE_SERVICE_ACCOUNT_BASE64 env var found.")
        return
    creds_json = base64.b64decode(creds_data).decode("utf-8")
    creds_dict = json.loads(creds_json)

    scope = ['https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gauth = GoogleAuth()
    gauth.credentials = credentials
    drive = GoogleDrive(gauth)

    folder_id = None
    file_list = drive.ListFile({
        'q': f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    }).GetList()
    if file_list:
        folder_id = file_list[0]['id']
    else:
        folder_metadata = {'title': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
        folder = drive.CreateFile(folder_metadata)
        folder.Upload()
        folder_id = folder['id']

    file_metadata = {'title': filename, 'parents': [{'id': folder_id}]}
    file = drive.CreateFile(file_metadata)
    file.SetContentFile(filename)
    file.Upload()
    print(f"Uploaded {filename} to Google Drive folder '{folder_name}'")

async def login_and_scrape(page):
    critiques = []

    base_url = "https://www.ourdogs.co.uk/app1/champshows.php"
    await page.goto(base_url)
    year_selectors = [
        'input[placeholder*="2025"]',
        'input[placeholder*="2024"]',
        'input[placeholder*="2023"]',
        'input[placeholder*="2022"]',
        'input[placeholder*="2021"]',
        'input[placeholder*="2020"]',
        'input[placeholder*="2019"]',
        'input[placeholder*="2018"]',
        'input[placeholder*="2017"]',
        'input[placeholder*="2016"]',
        'input[placeholder*="2015"]',
        'input[placeholder*="2014"]',
        'input[placeholder*="2013"]',
        'input[placeholder*="2012"]'
    ]

    for selector in year_selectors:
        try:
            await page.fill(selector, "RETRIEVER GOLDEN")
            await page.locator(f'{selector} ~ input[type="submit"]').click()
            await page.wait_for_selector("a:has-text('Championship Show')", timeout=10000)

            show_links = await page.locator('a:has-text("Championship Show")').all()
            for link in show_links:
                href = await link.get_attribute("href")
                if not href:
                    continue
                url = f"https://www.ourdogs.co.uk/app1/{href}"
                print(f"Scraping {url}")
                await page.goto(url)
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

                await page.goto(base_url)
        except Exception as e:
            print(f"Skipping year due to error: {e}")

    return critiques

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.ourdogs.co.uk/members/breedsearch1.php")
        page_content = await page.content()
        if "username" in page_content.lower():
            await page.fill('input[name="username"]', os.getenv("OURDOGS_USER"))
            await page.fill('input[name="password"]', os.getenv("OURDOGS_PASS"))
            await page.click('input[type="submit"]')
            await page.wait_for_load_state("networkidle")

        new_data = await login_and_scrape(page)

        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            seen = set((entry["show"], entry["year"]) for entry in existing_data)
        except FileNotFoundError:
            existing_data = []
            seen = set()

        fresh = []
        for entry in new_data:
            key = (entry["show"], entry["year"])
            if key not in seen:
                fresh.append(entry)
                seen.add(key)

        combined = existing_data + fresh
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2)

        upload_to_drive(RESULTS_FILE)
        await browser.close()
        print("Scraping complete.")
