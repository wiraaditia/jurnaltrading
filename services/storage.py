import os
import shutil
import uuid
from fastapi import UploadFile

# Folder fallback lokal
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Google Cloud Storage Configuration (Opsional)
# GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
# GCS_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

def save_image(file: UploadFile) -> str:
    """
    Saves image to storage (local fallback or GCS).
    Returns the URL/path to the image.
    """
    if not file or not file.filename:
        return ""

    # Generate unique filename
    extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{extension}"
    
    # GCS Upload logic (bisa diaktifkan jika credential di-set)
    # try:
    #     from google.cloud import storage
    #     if GCS_BUCKET_NAME and GCS_CREDENTIALS_PATH:
    #         client = storage.Client.from_service_account_json(GCS_CREDENTIALS_PATH)
    #         bucket = client.bucket(GCS_BUCKET_NAME)
    #         blob = bucket.blob(unique_filename)
    #         blob.upload_from_file(file.file)
    #         return blob.public_url
    # except Exception as e:
    #     print(f"Failed to upload to GCS, falling back to local storage: {e}")

    # Fallback to local storage
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Return local URL format
    return f"/uploads/{unique_filename}"
