from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
import pickle
import os
import io
import json

# Escopo básico do Google Drive (leitura e escrita)
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service():
    """Autentica e retorna o serviço do Google Drive."""
    creds = None
    if os.path.exists('token_drive.pkl'):
        with open('token_drive.pkl', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("⚠️ Erro: token inválido ou ausente. Rode auth_drive.py primeiro.")
    return build('drive', 'v3', credentials=creds)

# =============== UPLOAD DO ARQUIVO ===============
def upload_file(local_path, file_id):
    """Atualiza o arquivo existente no Drive com base no ID."""
    service = get_drive_service()
    media = MediaFileUpload(local_path, mimetype='application/json', resumable=True)
    updated = service.files().update(fileId=file_id, media_body=media).execute()
    print(f"✅ Upload concluído no Drive: {updated.get('id')}")

# =============== DOWNLOAD DO ARQUIVO ===============
def download_file(file_id, local_path):
    """Baixa o arquivo do Drive e salva localmente."""
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(local_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    print(f"📥 Arquivo baixado do Drive para {local_path}")

# =============== GARANTE QUE O ARQUIVO EXISTE ===============
def ensure_file_exists(file_id, local_path):
    """Se o arquivo não existir no Drive, cria um novo vazio e faz upload."""
    try:
        download_file(file_id, local_path)
    except HttpError as e:
        if e.resp.status == 404:
            print("⚠️ Arquivo não encontrado no Drive. Criando novo...")
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump({"reservas": []}, f, ensure_ascii=False, indent=2)
            upload_file(local_path, file_id)
            print("✅ Novo arquivo criado e enviado ao Drive.")
        else:
            raise
