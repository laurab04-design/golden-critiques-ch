import os
import json
import base64
import re
from playwright.async_api import async_playwright
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

BREED = "RETRIEVER GOLDEN"
RESULTS_FILE = "results.json"

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
    await page.goto("https://www.ourdogs.co.uk/members/breedsearch1.php")
    await page.fill('input[name="breed"]', BREED)
    await page.click('input[type="submit"]')
    await page.wait_for_selector("text=Championship Show Reports")

    show_links = await page.locator('a:has-text("Championship Show")').all()
    print(f"Found {len(show_links)} shows for {BREED}")

    critiques = []

    for i in range(len(show_links)):
        await page.goto("https://www.ourdogs.co.uk/members/breedsearch1.php")
        await page.fill('input[name="breed"]', BREED)
        await page.click('input[type="submit"]')
        await page.wait_for_selector("text=Championship Show Reports")
        show_links = await page.locator('a:has-text("Championship Show")').all()
        link = show_links[i]
        href = await link.get_attribute("href")
        url = f"https://www.ourdogs.co.uk/members/{href}"
        print(f"Scraping {url}")
        await page.goto(url)

        text = await page.text_content("body")

        show_match = re.search(r"Championship Show\s*-\s*(.*?)\s*\n", text)
        judge_match = re.search(r"\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\.\s*$", text.strip())

        show = show_match.group(1).strip() if show_match else "Unknown Show"
        judge = judge_match.group(1).strip() if judge_match else "Unknown"

        classes = re.findall(r"\n([A-Z]{2,4})\s*\((\d+),\s*(\d+)\)\s*(.*?)\n(?=[A-Z]{2,4}|\Z)", text, re.DOTALL)

        for class_code, entries, absents, block in classes:
            placements = re.findall(r"(\d)\s+([A-Za-z’'`&.\s]+)’s\s+(.*?)\.(.*?)?(?=\n\d|\n[A-Z]{2,4}|\Z)", block, re.DOTALL)
            entry = {
                "show": show,
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

        await page.goto("https://www.ourdogs.co.uk/members/breedsearch1.php")
        if "login" in await page.content().lower():
            await page.fill('input[name="username"]', os.getenv("OURDOGS_USER"))
            await page.fill('input[name="password"]', os.getenv("OURDOGS_PASS"))
            await page.click('input[type="submit"]')
            await page.wait_for_load_state("networkidle")

        data = await login_and_scrape(page)

        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        upload_to_drive(RESULTS_FILE)
        await browser.close()
        print("Scraping complete.")
