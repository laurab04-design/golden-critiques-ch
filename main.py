import os
import asyncio
from fastapi import FastAPI
from golden_critiques import run_scraper, upload_to_drive

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Golden Critiques Scraper API is live."}

@app.get("/run")
async def run():
    try:
        await run_scraper()
        upload_to_drive("golden_critiques.json")
        return {"status": "success", "message": "Scraper run completed and uploaded to Google Drive."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
