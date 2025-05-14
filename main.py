import os
from fastapi import FastAPI
from golden_critiques import run_scraper
from drive_utils import upload_to_drive

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Golden Critiques Scraper API is live."}

@app.get("/run")
async def run():
    try:
        await run_scraper()  # async Playwright
        upload_to_drive("golden_critiques.json", "application/json")  # sync upload
        return {"status": "success", "message": "Scraper run completed and uploaded to Google Drive."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
