import os
import json
import base64
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

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
