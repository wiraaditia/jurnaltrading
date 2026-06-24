import os
import shutil
import uuid
import json
from fastapi import UploadFile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Target Google Drive Folder ID
GDRIVE_FOLDER_ID = "1dTervmkO6pHsJjm7tcHOTxoi2tqezA4m"

# Path to service account key file (local testing)
# We search first in the project directory, then fallback to user's downloads folder if exists
LOCAL_KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "jurnal-trading-setup-96222a011b2e.json")
DOWNLOADS_KEY_PATH = r"C:\Users\gustu\Downloads\jurnal-trading-setup-96222a011b2e.json"

def get_google_drive_service():
    """
    Initializes and returns the Google Drive API service using Service Account credentials.
    """
    creds = None
    scopes = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

    # 1. Try to load from Environment Variable (for Vercel deployment)
    env_creds = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")
    if env_creds:
        try:
            creds_dict = json.loads(env_creds)
            creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        except Exception as e:
            print(f"Failed to load credentials from env: {e}")

    # 2. Fallback to local file (development)
    if not creds:
        key_path = None
        if os.path.exists(LOCAL_KEY_PATH):
            key_path = LOCAL_KEY_PATH
        elif os.path.exists(DOWNLOADS_KEY_PATH):
            key_path = DOWNLOADS_KEY_PATH

        if key_path:
            try:
                creds = service_account.Credentials.from_service_account_file(key_path, scopes=scopes)
            except Exception as e:
                print(f"Failed to load credentials from file {key_path}: {e}")

    if creds:
        return build("drive", "v3", credentials=creds)
    return None

# Folder fallback lokal
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_image(file: UploadFile) -> str:
    """
    Saves image to Google Drive, falls back to local storage if not available.
    Returns the URL/path to the image.
    """
    if not file or not file.filename:
        return ""

    # Generate unique filename
    extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{extension}"
    
    # Try Google Drive upload first
    try:
        service = get_google_drive_service()
        if service:
            # Metadata for Google Drive file
            file_metadata = {
                "name": unique_filename,
                "parents": [GDRIVE_FOLDER_ID]
            }
            
            # Prepare file stream
            media = MediaIoBaseUpload(file.file, mimetype=file.content_type, resumable=True)
            
            # Upload file
            uploaded_file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink, webContentLink"
            ).execute()
            
            file_id = uploaded_file.get("id")
            
            # Make the file public so anyone can view it
            user_permission = {
                "type": "anyone",
                "role": "reader",
            }
            service.permissions().create(
                fileId=file_id,
                body=user_permission
            ).execute()
            
            # Get the webViewLink (which works great for viewing or embedding)
            # Or construct direct download link:
            direct_link = f"https://lh3.googleusercontent.com/u/0/d/{file_id}"
            # Let's return a direct embeddable/viewable link or direct download link
            return f"https://drive.google.com/uc?export=view&id={file_id}"
            
    except Exception as e:
        print(f"Failed to upload to Google Drive, falling back to local storage: {e}")

    # Fallback to local storage
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    # Ensure seek is at 0 in case the stream was partially read
    try:
        file.file.seek(0)
    except Exception:
        pass
        
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Return local URL format
    return f"/uploads/{unique_filename}"
