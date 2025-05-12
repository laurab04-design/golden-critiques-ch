from pathlib import Path

# Save the provided scraper.py content to a file
scraper_code = """
import os
import asyncio
from playwright.async_api import async_playwright

OURDOGS_USER = os.getenv("OURDOGS_USER")
OURDOGS_PASS = os.getenv("OURDOGS_PASS")

LOGIN_URL = "https://www.ourdogs.co.uk/members/login.php"
INDEX_URL = "https://www.ourdogs.co.uk/members/gen-champshows/gen-chshow-index.php"

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(LOGIN_URL)
        await page.fill('input[name="user"]', OURDOGS_USER)
        await page.fill('input[name="pass"]', OURDOGS_PASS)
        await page.click('input[type="submit"]')

        await page.wait_for_timeout(2000)
        if INDEX_URL not in page.url:
            print("Login failed or redirected.")
            await browser.close()
            return

        await page.goto(INDEX_URL)
        await page.wait_for_timeout(1000)

        content = await page.content()
        print("Login succeeded and reached the index.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_scraper())
"""

# Write to file
file_path = Path("/mnt/data/scraper.py")
file_path.write_text(scraper_code)

file_path.name
