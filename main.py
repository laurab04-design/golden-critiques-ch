import os
import asyncio
from fastapi import FastAPI
from golden_critiques.scraper import run_scraper

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Golden Critiques Scraper API is live."}

@app.get("/run")
async def run():
    try:
        await run_scraper()
        return {"status": "success", "message": "Scraper run completed."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
