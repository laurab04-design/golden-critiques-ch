import os
import subprocess
subprocess.run(["playwright", "install", "chromium"], check=True)

from fastapi import FastAPI
from golden_critiques import run_scraper
from critique_parsing import process_all_files  # ← Your parser
from drive_utils import upload_to_drive

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Golden Critiques Scraper API is live."}

@app.get("/run")
async def run():
    try:
        await run_scraper()  # async: fetch .txts from Our Dogs

        # Run local critique parsing on synced Drive folder
        parsed = process_all_files("golden-critiques")
        output_path = os.path.join("golden-critiques", "golden_critiques_by_dog.json")
        with open(output_path, "w", encoding="utf-8") as f:
            import json
            json.dump(parsed, f, indent=2, ensure_ascii=False)

        upload_to_drive(output_path, "application/json", folder_name="golden-critiques")

        return {"status": "success", "message": "Scraper and parser run completed and uploaded."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
