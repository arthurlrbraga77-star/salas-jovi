from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import google.auth.transport.requests
import io
import os
import pickle
import base64

# ==========
# CONFIG
# ==========
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_ID = os.getenv("GOOGLE_FOLDER_ID")

def get_service():
    """Autentica com o Google Drive usando o token do ambiente (Render) ou arquivo local."""
    creds = None

    # 1️⃣ Tenta primeiro pegar o token do Render
    token_env = os.getenv("GOOGLE_TOKEN_PICKLE")
    if token_env:
        try:
            creds = pickle.loads(base64.b64decode(token_env.encode()))
            print("☁️ Token carregado do ambiente Render.")
        except Exception as e:
            print(f"⚠️ Erro ao decodificar token do ambiente: {e}")

    # 2️⃣ Se não tiver no ambiente, usa o arquivo local (modo de desenvolvimento)
    if not creds and os.path.exists("token_drive.pkl"):
        with open("token_drive.pkl", "rb") as token:
            creds = pickle.load(token)
        print("💾 Token carregado do arquivo local.")

    # 3️⃣ Se o token expirou, renova automaticamente
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        print("🔁 Token do Google renovado.")

    # 4️⃣ Cria o serviço do Drive
    service = build("drive", "v3", credentials=creds)
    return service


def upload_file(local_path, file_id=None):
    """Faz upload de um arquivo para o Google Drive (atualiza se já existir)."""
    service = get_service()
    file_metadata = {"name": os.path.basename(local_path), "parents": [FOLDER_ID]}
    media = MediaFileUpload(local_path, resumable=True)

    if file_id:
        updated = service.files().update(fileId=file_id, media_body=media).execute()
        print(f"✅ Arquivo atualizado no Drive: {updated['id']}")
    else:
        uploaded = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        print(f"✅ Arquivo enviado ao Drive: {uploaded['id']}")


def download_file(file_id, local_path):
    """Baixa um arquivo do Google Drive para o servidor local."""
    service = get_service()
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(local_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"⬇️  Download {int(status.progress() * 100)}%.")
    print(f"✅ Download concluído: {local_path}")
