from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import google.auth.transport.requests
import os
import io
import pickle
import base64
import json

# ============================
# CONFIGURAÇÃO
# ============================
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_ID = os.getenv("GOOGLE_FOLDER_ID")  # ID da pasta do Drive


def get_service():
    """Autentica com o Google Drive usando o token salvo localmente ou via Render."""
    creds = None

    # 1️⃣ Tenta pegar o token do Render (variável de ambiente codificada em Base64)
    token_env = os.getenv("GOOGLE_TOKEN_PICKLE")
    if token_env:
        try:
            creds = pickle.loads(base64.b64decode(token_env.encode()))
            print("☁️ Token carregado do ambiente (Render).")
        except Exception as e:
            print(f"⚠️ Erro ao decodificar token do ambiente: {e}")

    # 2️⃣ Caso não tenha token no ambiente, tenta o arquivo local
    if not creds and os.path.exists("token_drive.pkl"):
        with open("token_drive.pkl", "rb") as token:
            creds = pickle.load(token)
        print("💾 Token carregado do arquivo local.")

    # 3️⃣ Se o token expirou, renova automaticamente
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        print("🔁 Token do Google renovado.")

    # 4️⃣ Retorna o serviço autenticado
    service = build("drive", "v3", credentials=creds)
    return service


# ============================
# UPLOAD DO ARQUIVO
# ============================
def upload_file(local_path, folder_id):
    """Faz upload do arquivo JSON para a pasta correta no Drive."""
    service = get_service()
    file_name = os.path.basename(local_path)

    file_metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaFileUpload(local_path, mimetype="application/json", resumable=True)

    # Verifica se já existe um arquivo com o mesmo nome na pasta
    results = service.files().list(
        q=f"name='{file_name}' and '{folder_id}' in parents and trashed=false",
        spaces="drive",
        fields="files(id, name)"
    ).execute()

    files = results.get("files", [])
    if files:
        file_id = files[0]["id"]
        service.files().update(fileId=file_id, media_body=media).execute()
        print(f"🔁 Arquivo atualizado no Drive: {file_name}")
    else:
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        print(f"✅ Arquivo criado no Drive: {file_name}")


# ============================
# DOWNLOAD DO ARQUIVO
# ============================
def download_file(file_id, local_path):
    """Baixa o arquivo JSON do Drive para o servidor local."""
    service = get_service()
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(local_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"⬇️ Download {int(status.progress() * 100)}% concluído.")
    print(f"✅ Arquivo baixado: {local_path}")


# ============================
# GARANTE QUE O ARQUIVO EXISTA
# ============================
def ensure_file_exists(folder_id, local_path):
    """Verifica se o arquivo existe no Drive; se não, cria um novo."""
    service = get_service()
    file_name = os.path.basename(local_path)

    results = service.files().list(
        q=f"name='{file_name}' and '{folder_id}' in parents and trashed=false",
        spaces="drive",
        fields="files(id, name)"
    ).execute()

    files = results.get("files", [])
    if files:
        print(f"📂 Arquivo {file_name} já existe no Drive.")
        file_id = files[0]["id"]
        download_file(file_id, local_path)
    else:
        print("⚠️ Arquivo não encontrado no Drive. Criando um novo...")
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump({"reservas": []}, f, ensure_ascii=False, indent=2)
        upload_file(local_path, folder_id)
        print(f"✅ Novo arquivo {file_name} criado e enviado ao Drive.")
