from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

# Escopo mínimo para ler e escrever no Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def main():
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open('token_drive.pkl', 'wb') as token:
        pickle.dump(creds, token)
    print("✅ Autenticação concluída e token salvo como token_drive.pkl")

if __name__ == '__main__':
    main()
