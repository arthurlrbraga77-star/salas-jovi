# ===========================
#  WSGI - PYTHONANYWHERE (MODELO)
# ===========================
# Copie este conteúdo para o arquivo WSGI do web app no PythonAnywhere
# (aba "Web" -> "WSGI configuration file") e troque <USERNAME> pelo seu usuário.
import os
import sys

project_home = '/home/<USERNAME>/salas-jovi'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Senha de admin para cancelar reservas.
# A senha REAL fica SOMENTE no arquivo WSGI do PythonAnywhere, NUNCA no git.
# Escolha uma senha NOVA: não reutilize a senha antiga do sistema, ela está
# no histórico do git e qualquer pessoa com acesso ao repositório pode vê-la.
# Troque o texto entre aspas abaixo (inclusive os sinais < e >) pela senha.
SENHA_ADMIN = '<COLOQUE_A_SENHA_AQUI>'

# Enquanto o texto acima não for trocado (ainda começa com '<' e termina com '>'),
# o cancelamento de reservas fica desativado.
if SENHA_ADMIN.startswith('<') and SENHA_ADMIN.endswith('>'):
    SENHA_ADMIN = ''
os.environ['ADMIN_PASSWORD'] = SENHA_ADMIN

# Opcional: outro local para o banco (padrão: <project_home>/data/reservas.db)
# os.environ['RESERVAS_DB'] = '/home/<USERNAME>/salas-jovi/data/reservas.db'

from app import app as application  # noqa: E402
