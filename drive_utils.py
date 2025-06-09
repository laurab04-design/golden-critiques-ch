import os
import io
import json
import base64
import hashlib
from pathlib import Path
from collections import defaultdict

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


def upload_to_drive(filename: str, mime_type: str = None, folder_name: str = "golden-critiques"):
    creds_data = os.getenv("GOOGLE_SERVICE_ACCOUNT_BASE64")
    if not creds_data:
        print("GOOGLE_SERVICE_ACCOUNT_BASE64 not found in environment.")
        return

    # Decode credentials
    try:
        creds_json = base64.b64decode(creds_data + "==").decode("utf-8")
        creds_dict = json.loads(creds_json)
    except Exception as e:
        print(f"Failed to decode credentials: {e}")
        return

    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)

    # Get or create the folder
    folder_id = None
    folder_res = service.files().list(
        q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false",
        spaces='drive',
        fields='files(id, name)'
    ).execute()
    folders = folder_res.get("files", [])
    if folders:
        folder_id = folders[0]["id"]
    else:
        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder"
        }
        folder = service.files().create(body=folder_metadata, fields="id").execute()
        folder_id = folder["id"]

    # Compute local file's MD5
    def compute_md5(file_path):
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    local_md5 = compute_md5(filename)
    filename_only = Path(filename).name

    # Look for matching name + content in the folder
    dup_query = (
        f"name='{filename_only}' and '{folder_id}' in parents and trashed=false"
    )
    existing_files = service.files().list(
        q=dup_query,
        fields="files(id, md5Checksum, name)"
    ).execute().get("files", [])

    for existing in existing_files:
        remote_md5 = existing.get("md5Checksum")
        if remote_md5 == local_md5:
            print(f"[SKIPPED] Identical file already exists in Drive: {filename_only}")
            return  # Don't upload

    # Upload if no exact match found
    file_metadata = {
        'name': filename_only,
        'parents': [folder_id]
    }
    media = MediaFileUpload(filename, mimetype=mime_type)
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print(f"[UPLOADED] {filename_only} uploaded to Google Drive folder '{folder_name}'")


def deduplicate_drive_folder(folder_name: str = "golden-critiques"):
    creds_data = os.getenv("GOOGLE_SERVICE_ACCOUNT_BASE64")
    if not creds_data:
        print("GOOGLE_SERVICE_ACCOUNT_BASE64 not found in environment.")
        return

    try:
        creds_json = base64.b64decode(creds_data + "==").decode("utf-8")
        creds_dict = json.loads(creds_json)
    except Exception as e:
        print(f"Failed to decode credentials: {e}")
        return

    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)

    # Get folder ID
    folder_res = service.files().list(
        q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false",
        spaces='drive',
        fields='files(id, name)'
    ).execute()
    folders = folder_res.get("files", [])
    if not folders:
        print(f"[ERROR] Folder '{folder_name}' not found.")
        return
    folder_id = folders[0]["id"]

    # Get all non-trashed .txt files in the folder
    files = []
    page_token = None
    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType='text/plain'",
            spaces='drive',
            fields='nextPageToken, files(id, name, size)',
            pageToken=page_token
        ).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    # Group by (name, size)
    file_map = defaultdict(list)
    for f in files:
        name = f.get("name")
        size = f.get("size")
        if name and size:
            key = (name, size)
            file_map[key].append(f["id"])

    # Delete all but one in each group
    deleted_count = 0
    for key, file_ids in file_map.items():
        if len(file_ids) > 1:
            for dup_id in file_ids[1:]:
                try:
                    service.files().delete(fileId=dup_id).execute()
                    deleted_count += 1
                    print(f"[DEDUPLICATED] Deleted duplicate: {key[0]} (size {key[1]})")
                except Exception as e:
                    print(f"[ERROR] Failed to delete file {dup_id}: {e}")

    print(f"[DONE] Removed {deleted_count} duplicate files from '{folder_name}' using name + size.")


def download_from_drive(filename, folder_name="golden-critiques"):
    creds_data = os.getenv("GOOGLE_SERVICE_ACCOUNT_BASE64")
    if not creds_data:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_BASE64 not set")

    creds_json = base64.b64decode(creds_data + "==").decode("utf-8")
    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)

    # Find folder
    folder_list = service.files().list(
        q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed = false",
        spaces='drive',
        fields="files(id, name)"
    ).execute().get("files", [])
    if not folder_list:
        raise FileNotFoundError(f"Folder '{folder_name}' not found.")
    folder_id = folder_list[0]["id"]

    # Find file
    file_list = service.files().list(
        q=f"name='{filename}' and '{folder_id}' in parents and trashed = false",
        spaces='drive',
        fields="files(id, name)"
    ).execute().get("files", [])
    if not file_list:
        raise FileNotFoundError(f"File '{filename}' not found in folder '{folder_name}'.")

    file_id = file_list[0]["id"]
    request = service.files().get_media(fileId=file_id)
    local_path = f"/tmp/{filename}"
    fh = io.FileIO(local_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    print(f"Downloaded {filename} to {local_path}")
    return local_path
