import os
import io
import json
import base64
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

def upload_to_drive(filename: str, mime_type: str = None, folder_name: str = "golden-critiques"):
    creds_data = os.getenv("GOOGLE_SERVICE_ACCOUNT_BASE64")
    if not creds_data:
        print("GOOGLE_SERVICE_ACCOUNT_BASE64 not found in environment.")
        return

    # Decode base64 and load JSON
    try:
        creds_json = base64.b64decode(creds_data + "==").decode("utf-8")
        creds_dict = json.loads(creds_json)
    except Exception as e:
        print(f"Failed to decode credentials: {e}")
        return

    # Authenticate
    scope = ['https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gauth = GoogleAuth()
    gauth.credentials = credentials
    drive = GoogleDrive(gauth)

    # Find or create folder
    folder_id = None
    query = f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    folder_list = drive.ListFile({'q': query}).GetList()
    if folder_list:
        folder_id = folder_list[0]['id']
    else:
        folder_metadata = {
            'title': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = drive.CreateFile(folder_metadata)
        folder.Upload()
        folder_id = folder['id']

    # Upload file
    file_metadata = {'title': os.path.basename(filename), 'parents': [{'id': folder_id}]}
    if mime_type:
        file_metadata['mimeType'] = mime_type

    file = drive.CreateFile(file_metadata)
    file.SetContentFile(filename)
    file.Upload()
    print(f"Uploaded {filename} to Google Drive folder '{folder_name}'")

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

    return local_path
