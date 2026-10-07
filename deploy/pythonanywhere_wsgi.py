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
# Enquanto o placeholder não for trocado, o cancelamento fica desativado.
SENHA_ADMIN = '<COLOQUE_A_SENHA_AQUI>'
os.environ['ADMIN_PASSWORD'] = '' if SENHA_ADMIN == '<COLOQUE_A_SENHA_AQUI>' else SENHA_ADMIN

# Opcional: outro local para o banco (padrão: <project_home>/data/reservas.db)
# os.environ['RESERVAS_DB'] = '/home/<USERNAME>/salas-jovi/data/reservas.db'

from app import app as application  # noqa: E402
