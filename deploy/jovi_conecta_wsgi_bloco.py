# ======================================================================
#  SALAS JOVI DENTRO DO JOVI CONECTA - BLOCO PARA O WSGI (PYTHONANYWHERE)
# ======================================================================
# Cole este bloco INTEIRO no FINAL do arquivo WSGI do JOVI Conecta, DEPOIS da linha
#     from flask_app import app as application
# Os valores reais ficam SOMENTE no PythonAnywhere: este repositório é PÚBLICO.
#
# 1) TOKEN da URL (vai no QR code). Gere um no console Bash do PythonAnywhere:
#        python3 -c "import secrets; print(secrets.token_urlsafe(24))"
#    e troque o texto entre < > da linha "token = ..." (inclusive os sinais < e >)
#    pelo token gerado, MANTENDO as aspas ("substituir tudo" do editor serve).
# 2) SENHA de admin (para cancelar reservas): NÃO vai neste arquivo. Escreva a senha,
#    sozinha, no arquivo /home/arthurbraga/.salas_jovi_senha (aba "Files").
#    Pode ter qualquer caractere; espaços/quebras de linha no começo e no fim são
#    ignorados. Sem esse arquivo (ou vazio), o cancelamento fica desativado.
# 3) ANTES do "Reload", confira se o arquivo WSGI continua com Python válido
#    (o caminho dele aparece na aba "Web", em "WSGI configuration file"):
#        python3 -c "import sys; compile(open(sys.argv[1], 'rb').read(), 'wsgi', 'exec'); print('OK')" /var/www/www_joviconectasp_com_br_wsgi.py
#    Um erro de digitação (ex.: aspas apagadas) derruba o JOVI inteiro: o try/except
#    abaixo só protege contra falhas na hora de rodar, não contra erro de sintaxe.
#
# - Requisições em /salas/<token> (com ou sem barra final) vão para o app de salas.
# - TODAS as outras vão para o JOVI Conecta exatamente como chegaram (mesmo environ).
# - Se algo falhar aqui, "application" continua sendo o JOVI Conecta (o erro vai
#   para o error log) e o JOVI segue funcionando como antes.
try:
    def _salas_montar(app_jovi):
        import importlib.util
        import os
        import re
        import sys

        # Token secreto: só letras, números, - e _ (mín. 20)
        token = "<TROQUE_PELO_TOKEN_SECRETO_DAS_SALAS>"
        arquivo_senha = "/home/arthurbraga/.salas_jovi_senha"
        arquivo_app = "/home/arthurbraga/salas-jovi/app.py"

        # Token não trocado (ainda tem < >), curto ou com caracteres estranhos: não monta
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,}", token):
            print("[salas-jovi] token ausente ou invalido: app de salas NAO montado", file=sys.stderr)
            return app_jovi

        # Senha lida de um arquivo fora do repositório (nunca escrita como texto Python)
        try:
            with open(arquivo_senha, encoding="utf-8") as f:
                senha = f.read().strip()
        except (OSError, ValueError):
            senha = ""

        # Carrega o app.py das salas com um nome de módulo único e SEM mexer no
        # sys.path (nenhum arquivo da pasta das salas "esconde" um módulo do JOVI).
        # Registrar em sys.modules ANTES do exec: o Flask usa isso para achar
        # templates/ e static/ na pasta do app.py.
        nome = "salas_jovi_app"
        spec = importlib.util.spec_from_file_location(nome, arquivo_app)
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[nome] = modulo
        try:
            spec.loader.exec_module(modulo)
            app_salas = modulo.app
            os.environ["SALAS_ADMIN_PASSWORD"] = senha  # vazia = cancelamento desativado
        except BaseException:
            sys.modules.pop(nome, None)
            raise

        prefixo = "/salas/" + token
        prefixo_barra = prefixo + "/"

        def application(environ, start_response):
            caminho = environ.get("PATH_INFO", "")
            if caminho == prefixo or caminho.startswith(prefixo_barra):
                environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + prefixo
                environ["PATH_INFO"] = caminho[len(prefixo):]
                return app_salas(environ, start_response)
            return app_jovi(environ, start_response)  # JOVI Conecta: environ intocado

        aviso = "" if senha else " (cancelamento DESATIVADO: sem senha em " + arquivo_senha + ")"
        print("[salas-jovi] app de salas montado" + aviso, file=sys.stderr)
        return application

    application = _salas_montar(application)
except (Exception, SystemExit) as _salas_erro:  # SystemExit: um sys.exit() no app.py
    try:
        import sys as _salas_sys
        print(f"[salas-jovi] app de salas NAO montado (JOVI segue normal): {_salas_erro!r}",
              file=_salas_sys.stderr)
    except Exception:
        pass
