# ===========================
#  TESTES DO BLOCO WSGI DENTRO DO JOVI CONECTA
# ===========================
# O app de salas roda DENTRO do processo do JOVI Conecta (sistema de produção),
# montado em /salas/<token> pelo bloco deploy/jovi_conecta_wsgi_bloco.py.
# Aqui um JOVI Conecta FALSO (catch-all, login obrigatório, /static e
# /api/reservas próprios) recebe o bloco REAL colado no fim do seu arquivo WSGI,
# do mesmo jeito que no PythonAnywhere. A regra principal: para tudo que não é
# /salas/<token>, o JOVI recebe o MESMO environ, sem nenhuma alteração.
# Rodar com:  python3 -m pytest -q tests
import importlib.util
import json
import os
import subprocess
import sys
import types
from urllib.parse import quote

import pytest
from flask import Flask, jsonify, redirect, request, url_for
from werkzeug.test import Client, EnvironBuilder

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO_BLOCO = os.path.join(RAIZ, "deploy", "jovi_conecta_wsgi_bloco.py")
APP_PY = os.path.join(RAIZ, "app.py")

# Texto do bloco que o dono troca no PythonAnywhere ("substituir tudo") e caminhos
# que os testes trocam por arquivos temporários
TEXTO_TOKEN = "<TROQUE_PELO_TOKEN_SECRETO_DAS_SALAS>"
CAMINHO_NO_PA = "/home/arthurbraga/salas-jovi/app.py"
CAMINHO_SENHA_NO_PA = "/home/arthurbraga/.salas_jovi_senha"

NOME_MODULO = "salas_jovi_app"
TOKEN = "Tst_token-0123456789abcdefXYZ"  # só para os testes
PREFIXO = "/salas/" + TOKEN
SENHA = "senha-de-teste-do-bloco"

# Imitação do final do arquivo WSGI do JOVI Conecta no PythonAnywhere
CABECALHO_WSGI_JOVI = """\
import sys
# ... configuração do JOVI Conecta ...
from flask_app import app as application  # noqa
"""


# ===========================
#  JOVI CONECTA FALSO
# ===========================
def criar_jovi_falso(pasta):
    """Imita um app grande de produção, com rotas que colidiriam com as das salas."""
    (pasta / "static").mkdir(parents=True, exist_ok=True)
    (pasta / "static" / "x.css").write_text("body { color: red }", encoding="utf-8")
    jovi = Flask("jovi_conecta_falso", root_path=str(pasta))

    @jovi.before_request
    def exigir_login():
        if request.endpoint in ("login", "static"):
            return None
        if request.cookies.get("jovi_sessao") != "ok":
            return redirect(url_for("login", next=request.full_path))
        return None

    @jovi.after_request
    def marca_do_jovi(resposta):
        resposta.headers["X-JOVI"] = "1"
        return resposta

    @jovi.route("/login", methods=["GET", "POST"])
    def login():
        return "JOVI login"

    @jovi.route("/api/reservas", methods=["GET", "POST"])
    def reservas_do_jovi():
        return jsonify(app="jovi", rota="api_reservas", metodo=request.method)

    @jovi.route("/", defaults={"p": ""}, methods=["GET", "POST", "PUT", "DELETE"])
    @jovi.route("/<path:p>", methods=["GET", "POST", "PUT", "DELETE"])
    def eco(p):
        return jsonify(app="jovi", p=p, script_root=request.script_root, path=request.path,
                       full_path=request.full_path, metodo=request.method,
                       corpo=request.get_data(as_text=True))

    # Grava cada environ que chega ao JOVI: o objeto e uma cópia do conteúdo NA ENTRADA
    jovi.recebidos = []
    wsgi_original = jovi.wsgi_app

    def gravar(environ, start_response):
        jovi.recebidos.append((environ, dict(environ)))
        return wsgi_original(environ, start_response)

    jovi.wsgi_app = gravar
    return jovi


# ===========================
#  FIXTURES E AJUDANTES
# ===========================
def ler_bloco():
    with open(ARQUIVO_BLOCO, encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Banco temporário, sys.path/sys.modules/env restaurados no fim e um JOVI falso."""
    monkeypatch.setenv("SALAS_RESERVAS_DB", str(tmp_path / "db" / "reservas.db"))
    monkeypatch.delenv("RESERVAS_DB", raising=False)
    monkeypatch.delenv("SALAS_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(sys.modules, NOME_MODULO, None)  # no fim volta ao estado original
    del sys.modules[NOME_MODULO]

    jovi = criar_jovi_falso(tmp_path / "jovi")
    flask_app = types.ModuleType("flask_app")  # o "from flask_app import app" do WSGI
    flask_app.app = jovi
    monkeypatch.setitem(sys.modules, "flask_app", flask_app)
    return types.SimpleNamespace(tmp=tmp_path, jovi=jovi)


def carregar_wsgi(amb, token=TOKEN, senha=SENHA, arquivo_app=APP_PY, bloco=None, cabecalho=CABECALHO_WSGI_JOVI):
    """Cola o bloco no fim do WSGI do JOVI (trocando o token com "substituir tudo"),
    grava a senha no arquivo de senha (senha=None: arquivo não existe) e carrega o
    arquivo WSGI como módulo, como o PythonAnywhere faz."""
    texto = ler_bloco() if bloco is None else bloco
    if token is not None:
        texto = texto.replace(TEXTO_TOKEN, token)
    arquivo_senha = amb.tmp / "home" / ".salas_jovi_senha"
    if senha is not None:
        arquivo_senha.parent.mkdir(parents=True, exist_ok=True)
        arquivo_senha.write_text(senha, encoding="utf-8")
    texto = texto.replace(CAMINHO_NO_PA, arquivo_app).replace(CAMINHO_SENHA_NO_PA, str(arquivo_senha))

    arquivo = amb.tmp / "www_joviconectasp_com_br_wsgi.py"
    arquivo.write_text(cabecalho + "\n" + texto, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("wsgi_jovi_conecta_teste", str(arquivo))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def montado(ambiente, capsys):
    wsgi = carregar_wsgi(ambiente)
    assert wsgi.application is not ambiente.jovi
    assert "[salas-jovi] app de salas montado" in capsys.readouterr().err
    ambiente.application = wsgi.application
    return ambiente


def cru(texto):
    """Caminho como aparece no environ WSGI (bytes UTF-8 lidos como latin-1)."""
    return texto.encode("utf-8").decode("latin-1")


def novo_environ(caminho, query="", metodo="GET", logado=True, **kw):
    env = EnvironBuilder(path="/", method=metodo, query_string=query, **kw).get_environ()
    env["PATH_INFO"] = cru(caminho)
    uri = quote(caminho, safe="/%") + ("?" + query if query else "")
    env["REQUEST_URI"] = env["RAW_URI"] = uri
    if logado:
        env["HTTP_COOKIE"] = "jovi_sessao=ok"
    return env


def chamar(app, environ):
    """Chama o app WSGI como um servidor faria, com ESTE environ (o run_wsgi_app do
    werkzeug faz uma cópia, o que esconderia se o JOVI recebe o mesmo objeto)."""
    resposta = {}

    def start_response(status, cabecalhos, exc_info=None):
        resposta["status"], resposta["cabecalhos"] = status, list(cabecalhos)
        return lambda dados: None

    iteravel = app(environ, start_response)
    try:
        corpo = b"".join(iteravel)
    finally:
        if hasattr(iteravel, "close"):
            iteravel.close()
    return resposta["status"], resposta["cabecalhos"], corpo


def sem_streams(env):
    return {k: v for k, v in env.items() if k not in ("wsgi.input", "wsgi.errors")}


def conferir_jovi_intocado(amb, application, env_fabrica):
    """O JOVI recebe o MESMO dict, sem nenhuma chave alterada, e responde igual."""
    jovi = amb.jovi

    env_direto = env_fabrica()
    jovi.recebidos.clear()
    resposta_direta = chamar(jovi, env_direto)          # sem o bloco
    (_, conteudo_direto), = jovi.recebidos

    env = env_fabrica()
    copia = dict(env)
    jovi.recebidos.clear()
    resposta = chamar(application, env)                  # com o bloco
    assert len(jovi.recebidos) == 1
    recebido, conteudo_na_entrada = jovi.recebidos[0]
    assert recebido is env                               # o mesmo objeto
    assert conteudo_na_entrada == copia                  # nada mudou, nada foi adicionado
    assert sem_streams(conteudo_na_entrada) == sem_streams(conteudo_direto)
    assert resposta == resposta_direta                   # status, cabeçalhos e corpo idênticos
    assert all(nome != "X-Robots-Tag" for nome, _ in resposta[1])  # hooks das salas não vazam
    return resposta


CAMINHOS_DO_JOVI = [
    "/", "/login", "/logout", "/api/reservas", "/api/reservas/delete", "/static/x.css",
    "/static/nao-existe.css", "/static/style.css", "/static/script.js",
    "/salas", "/salas/", "/salas/WRONGTOKEN/", "/salas/WRONGTOKEN", "/salas/WRONGTOKEN/api/reservas",
    f"/salas/{TOKEN}x", f"/salas/{TOKEN}x/", f"/salas/{TOKEN}-/api/reservas", f"/salas/{TOKEN}.css",
    f"/salas/{TOKEN[:-1]}", f"/salas/{TOKEN[:-1]}/", f"/salas/{TOKEN} ", f"/salas/{TOKEN}%2F",
    f"/salas/{TOKEN}\\", f"/SALAS/{TOKEN}/", f"/Salas/{TOKEN}", f"/salas/{TOKEN.upper()}/",
    f"/salas/{TOKEN.lower()}/", f"//salas/{TOKEN}/", f"/salas//{TOKEN}/", f"/x/salas/{TOKEN}/",
    f"/{TOKEN}/", f"/salas/ {TOKEN}/", f"/salas{TOKEN}/", "//", "//login", "/salas//",
    "/ação/çé", "/salas/ção", "/日本語/ページ", "/a b/c", "/static/../login", "/static%2Fx.css",
    "",
]


# ===========================
#  JOVI CONECTA INTOCADO
# ===========================
@pytest.mark.parametrize("logado", [True, False], ids=["logado", "sem_login"])
@pytest.mark.parametrize("caminho", CAMINHOS_DO_JOVI)
def test_jovi_recebe_environ_identico_e_responde_igual(montado, caminho, logado):
    conferir_jovi_intocado(montado, montado.application, lambda: novo_environ(caminho, logado=logado))


@pytest.mark.parametrize("caminho, query", [
    ("/", f"next={PREFIXO}/"),
    ("/login", "a=1&b=%C3%A7&c="),
    ("/salas", f"t={TOKEN}"),
    ("/salas/", f"{TOKEN}"),
    (f"/salas/{TOKEN}x", "x=1"),
    ("/api/reservas", "sala=samba&inicio=2030-01-07"),
    ("/busca", "q=" + quote(PREFIXO, safe="")),
])
def test_jovi_com_query_string(montado, caminho, query):
    status, _, corpo = conferir_jovi_intocado(montado, montado.application,
                                              lambda: novo_environ(caminho, query=query))
    assert status == "200 OK"
    assert corpo == b"JOVI login" or json.loads(corpo)["app"] == "jovi"


@pytest.mark.parametrize("metodo, caminho, corpo", [
    ("POST", "/api/reservas", b'{"data": "2030-01-07T08:00", "sala": "samba"}'),
    ("POST", "/login", b"usuario=a&senha=b"),
    ("PUT", "/clientes/7", b"x"),
    ("DELETE", "/clientes/7", b""),
    ("POST", f"/salas/{TOKEN}x/api/reservas", b"{}"),
    ("HEAD", "/", b""),
    ("OPTIONS", "/api/reservas", b""),
])
def test_jovi_outros_metodos_e_corpo(montado, metodo, caminho, corpo):
    conferir_jovi_intocado(montado, montado.application,
                           lambda: novo_environ(caminho, metodo=metodo, data=corpo))


def test_jovi_rotas_proprias_continuam_do_jovi(montado):
    c = Client(montado.application)
    c.set_cookie("jovi_sessao", "ok")
    assert c.get("/api/reservas").get_json() == {"app": "jovi", "rota": "api_reservas", "metodo": "GET"}
    css = c.get("/static/x.css")
    assert css.get_data(as_text=True) == "body { color: red }"
    css.close()
    eco = c.get(f"/salas/{TOKEN}x/").get_json()
    assert eco["app"] == "jovi" and eco["script_root"] == "" and eco["path"] == f"/salas/{TOKEN}x/"
    sem_login = Client(montado.application).get("/salas/")
    assert sem_login.status_code == 302 and sem_login.headers["Location"].startswith("/login")


def test_environ_minimo_sem_script_name_nem_path_info(montado):
    """Servidor que não manda SCRIPT_NAME (nem PATH_INFO): nenhuma chave é criada."""
    def fabrica(sem):
        def env():
            e = novo_environ("/qualquer")
            for chave in sem:
                del e[chave]
            return e
        return env
    for sem in (["SCRIPT_NAME"], ["PATH_INFO"], ["SCRIPT_NAME", "PATH_INFO"]):
        conferir_jovi_intocado(montado, montado.application, fabrica(sem))
        recebido = montado.jovi.recebidos[0][0]
        assert not any(chave in recebido for chave in sem)


# ===========================
#  APP DE SALAS SOB O PREFIXO
# ===========================
def assert_privado(res):
    assert res.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert res.headers["Referrer-Policy"] == "no-referrer"
    assert "X-JOVI" not in res.headers


@pytest.mark.parametrize("final", ["", "/"], ids=["sem_barra", "com_barra"])
def test_pagina_de_salas_e_estaticos_sob_o_prefixo(montado, final):
    c = Client(montado.application)  # sem cookie do JOVI: não passa pelo login dele
    res = c.get(PREFIXO + final)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Meeting Room Booking" in html
    assert f'window.SALAS_BASE = "{PREFIXO}";' in html
    assert '<meta name="robots" content="noindex, nofollow"' in html
    assert_privado(res)

    for nome, tipo in [("style.css", "text/css"), ("script.js", "javascript"), ("jovi_logo_topbar.png", "image/png"),
                       ("jovi_logo.png", "image/png")]:
        if nome != "jovi_logo.png":  # a logo original continua servida, mas a página usa a cópia leve
            assert f"{PREFIXO}/static/{nome}" in html
        estatico = c.get(f"{PREFIXO}/static/{nome}")
        assert estatico.status_code == 200 and tipo in estatico.content_type
        with open(os.path.join(RAIZ, "static", nome), "rb") as f:
            assert estatico.data == f.read()
        assert_privado(estatico)
        estatico.close()

    assert montado.jovi.recebidos == []  # nada disso chegou ao JOVI


def test_api_de_salas_sob_o_prefixo(montado):
    c = Client(montado.application)
    item = {"data": "2030-01-07T08:00", "nome": "Reunião", "email": "a@jovimobile.com",
            "duracao": 0.5, "idRepeticao": "x", "sala": "samba"}

    res = c.post(f"{PREFIXO}/api/reservas", json=item)
    assert res.status_code == 201 and res.get_json() == {"status": "ok", "count": 1}
    assert_privado(res)
    assert c.post(f"{PREFIXO}/api/reservas", json=item).status_code == 409

    lista = c.get(f"{PREFIXO}/api/reservas?sala=samba&inicio=2030-01-07&fim=2030-01-11").get_json()["reservas"]
    assert [(r["data"], r["nome"]) for r in lista] == [("2030-01-07T08:00", "Reunião")]
    assert os.path.exists(montado.tmp / "db" / "reservas.db")  # banco temporário

    corpo = {"id": lista[0]["idRepeticao"], "sala": "samba"}
    assert c.post(f"{PREFIXO}/api/reservas/delete", json=dict(corpo, senha="errada")).status_code == 403
    res = c.post(f"{PREFIXO}/api/reservas/delete", json=dict(corpo, senha=SENHA))
    assert res.status_code == 200 and res.get_json()["deleted"] == 1
    assert c.get(f"{PREFIXO}/api/reservas").get_json() == {"reservas": []}

    erro = c.get(f"{PREFIXO}/nao-existe")
    assert erro.status_code == 404
    assert_privado(erro)
    assert montado.jovi.recebidos == []  # o /api/reservas do JOVI nunca foi chamado


def test_reescrita_do_environ_das_salas(montado):
    env = novo_environ(PREFIXO + "/api/reservas", query="sala=samba", logado=False)
    env["SCRIPT_NAME"] = "/raiz"  # servidor que já usa um SCRIPT_NAME
    status, _, _ = chamar(montado.application, env)
    assert status == "200 OK"
    assert env["SCRIPT_NAME"] == "/raiz" + PREFIXO and env["PATH_INFO"] == "/api/reservas"

    env = novo_environ(PREFIXO, logado=False)
    env["SCRIPT_NAME"] = "/raiz"
    status, _, corpo = chamar(montado.application, env)
    assert status == "200 OK"
    assert f'window.SALAS_BASE = "/raiz{PREFIXO}";' in corpo.decode("utf-8")
    assert montado.jovi.recebidos == []


@pytest.mark.parametrize("senha", [None, "", "  \n\n"], ids=["sem_arquivo", "vazio", "so_espacos"])
def test_sem_senha_desativa_so_o_cancelamento(ambiente, capsys, senha):
    wsgi = carregar_wsgi(ambiente, senha=senha)
    assert wsgi.application is not ambiente.jovi
    assert os.environ["SALAS_ADMIN_PASSWORD"] == ""
    linhas = capsys.readouterr().err.strip().splitlines()
    assert len(linhas) == 1 and "montado (cancelamento DESATIVADO" in linhas[0]
    c = Client(wsgi.application)
    assert c.get(PREFIXO + "/").status_code == 200
    res = c.post(f"{PREFIXO}/api/reservas/delete", json={"id": "x", "senha": ""})
    assert res.status_code == 503


def test_senha_ilegivel_desativa_so_o_cancelamento(ambiente, capsys):
    (ambiente.tmp / "home" / ".salas_jovi_senha").mkdir(parents=True)  # pasta: IsADirectoryError
    wsgi = carregar_wsgi(ambiente, senha=None)
    assert wsgi.application is not ambiente.jovi
    assert os.environ["SALAS_ADMIN_PASSWORD"] == ""


def test_senha_definida_pelo_arquivo(montado):
    assert os.environ["SALAS_ADMIN_PASSWORD"] == SENHA


SENHAS_DIFICEIS = ['abc"def', "abc\\", "Jovi\\N2025", "pa\\x4ss", "C:\\novo\\tst",
                   "x'y\"z\"\"\"", "çãé 日本 !@#$%", "  com espaços nas pontas  \n"]


@pytest.mark.parametrize("senha", SENHAS_DIFICEIS)
def test_qualquer_senha_funciona_e_nunca_quebra_o_wsgi(ambiente, capsys, senha):
    """A senha fica num arquivo, nunca no texto Python do WSGI: aspas, barras
    invertidas e acentos não causam erro de sintaxe nem viram outros caracteres."""
    wsgi = carregar_wsgi(ambiente, senha=senha)
    assert wsgi.application is not ambiente.jovi
    assert os.environ["SALAS_ADMIN_PASSWORD"] == senha.strip()
    assert senha.strip() not in capsys.readouterr().err

    c = Client(wsgi.application)
    item = {"data": "2030-01-07T08:00", "nome": "n", "email": "e", "duracao": 0.5, "sala": "samba"}
    assert c.post(f"{PREFIXO}/api/reservas", json=item).status_code == 201
    id_rep = c.get(f"{PREFIXO}/api/reservas").get_json()["reservas"][0]["idRepeticao"]
    assert c.post(f"{PREFIXO}/api/reservas/delete", json={"id": id_rep, "senha": senha + "x"}).status_code == 403
    res = c.post(f"{PREFIXO}/api/reservas/delete", json={"id": id_rep, "senha": senha.strip()})
    assert res.status_code == 200


def test_bloco_compila_com_qualquer_token_valido():
    """O único texto que o dono cola no WSGI é o token (saída do token_urlsafe)."""
    import secrets
    for _ in range(50):
        texto = CABECALHO_WSGI_JOVI + ler_bloco().replace(TEXTO_TOKEN, secrets.token_urlsafe(24))
        compile(texto, "wsgi.py", "exec")


def test_banco_generico_reservas_db_do_jovi_e_ignorado(ambiente, monkeypatch):
    """Se o processo do JOVI tiver RESERVAS_DB, o app de salas NÃO abre esse banco."""
    banco_do_jovi = ambiente.tmp / "jovi" / "jovi.db"
    banco_do_jovi.parent.mkdir(parents=True, exist_ok=True)
    banco_do_jovi.write_bytes(b"conteudo do JOVI")
    monkeypatch.setenv("RESERVAS_DB", str(banco_do_jovi))

    c = Client(carregar_wsgi(ambiente).application)
    item = {"data": "2030-01-07T08:00", "nome": "n", "email": "e", "duracao": 0.5, "sala": "samba"}
    assert c.post(f"{PREFIXO}/api/reservas", json=item).status_code == 201
    assert len(c.get(f"{PREFIXO}/api/reservas").get_json()["reservas"]) == 1
    assert banco_do_jovi.read_bytes() == b"conteudo do JOVI"
    assert os.path.exists(ambiente.tmp / "db" / "reservas.db")


# ===========================
#  FALHAS: O JOVI CONTINUA EXATAMENTE COMO ANTES
# ===========================
def preparar_falha(amb, caso):
    """Devolve os argumentos de carregar_wsgi para cada tipo de falha."""
    falso = amb.tmp / "salas_quebrado" / "app.py"
    falso.parent.mkdir(exist_ok=True)
    if caso == "arquivo_inexistente":
        return {"arquivo_app": str(amb.tmp / "nao_existe" / "app.py")}
    if caso == "app_py_levanta_erro":
        falso.write_text("import os\nraise RuntimeError('falha ao importar')\n", encoding="utf-8")
    elif caso == "app_py_erro_de_sintaxe":
        falso.write_text("def quebrado(:\n", encoding="utf-8")
    elif caso == "app_py_sem_app":
        falso.write_text("x = 1\n", encoding="utf-8")
    elif caso == "app_py_chama_sys_exit":
        falso.write_text("import sys\nsys.exit('config ausente')\n", encoding="utf-8")
    elif caso == "app_py_sys_exit_sem_codigo":
        falso.write_text("raise SystemExit\n", encoding="utf-8")
    elif caso == "senha_com_byte_nulo":
        return {"senha": "abc\x00def"}  # os.environ recusa: falha DEPOIS do import
    elif caso == "app_py_import_inexistente":
        falso.write_text("import modulo_que_nao_existe_xyz\n", encoding="utf-8")
    elif caso == "token_nao_trocado":
        return {"token": None}
    elif caso == "token_vazio":
        return {"token": ""}
    elif caso == "token_curto":
        return {"token": "abc123"}
    elif caso == "token_com_barra":
        return {"token": "abc/def/ghi/jkl/mno/pqr"}
    elif caso == "token_com_espaco":
        return {"token": " " + TOKEN}
    elif caso == "token_com_sinais":
        return {"token": "<" + TOKEN + ">"}
    return {"arquivo_app": str(falso)}


CASOS_DE_FALHA = [
    "arquivo_inexistente", "app_py_levanta_erro", "app_py_erro_de_sintaxe", "app_py_sem_app",
    "app_py_chama_sys_exit", "app_py_sys_exit_sem_codigo", "senha_com_byte_nulo",
    "app_py_import_inexistente", "token_nao_trocado", "token_vazio", "token_curto",
    "token_com_barra", "token_com_espaco", "token_com_sinais",
]


@pytest.mark.parametrize("caso", CASOS_DE_FALHA)
def test_falha_deixa_application_original(ambiente, capsys, caso):
    wsgi = carregar_wsgi(ambiente, **preparar_falha(ambiente, caso))  # não pode levantar erro

    assert wsgi.application is ambiente.jovi  # o MESMO objeto
    assert NOME_MODULO not in sys.modules
    linhas = capsys.readouterr().err.strip().splitlines()
    assert len(linhas) == 1 and linhas[0].startswith("[salas-jovi]") and "NAO montado" in linhas[0]
    assert TOKEN not in linhas[0] and SENHA not in linhas[0]
    assert "SALAS_ADMIN_PASSWORD" not in os.environ  # nem mexeu no ambiente do processo

    for caminho in ("/", "/login", "/api/reservas", "/static/x.css", PREFIXO, PREFIXO + "/"):
        for logado in (True, False):
            conferir_jovi_intocado(ambiente, wsgi.application,
                                   lambda: novo_environ(caminho, logado=logado))


def test_bloco_colado_antes_do_application_nao_quebra(ambiente, capsys):
    wsgi = carregar_wsgi(ambiente, cabecalho="import sys\n")
    assert not hasattr(wsgi, "application")
    linhas = capsys.readouterr().err.strip().splitlines()
    assert len(linhas) == 1 and "NameError" in linhas[0]


def test_textos_para_trocar_aparecem_uma_vez_so():
    """"Substituir tudo" no editor troca exatamente o valor (nunca uma comparação)."""
    bloco = ler_bloco()
    assert bloco.count(TEXTO_TOKEN) == 1
    assert bloco.count(CAMINHO_NO_PA) == 1
    assert CAMINHO_SENHA_NO_PA in bloco
    assert "<TROQUE" not in bloco.replace(TEXTO_TOKEN, TOKEN)
    # o código (sem comentários) não usa DispatcherMiddleware nem mexe no sys.path
    codigo = "\n".join(linha.split("#")[0] for linha in bloco.splitlines())
    assert "DispatcherMiddleware" not in codigo and "werkzeug" not in codigo
    assert "sys.path" not in codigo


# ===========================
#  ISOLAMENTO DE MÓDULOS (SYS.PATH / SYS.MODULES)
# ===========================
def test_bloco_nao_mexe_no_sys_path_nem_esconde_modulos(ambiente, monkeypatch):
    app_do_jovi = types.ModuleType("app")  # o JOVI pode ter um módulo chamado "app"
    app_do_jovi.QUEM = "jovi"
    monkeypatch.setitem(sys.modules, "app", app_do_jovi)

    path_antes = list(sys.path)
    modulos_antes = dict(sys.modules)
    wsgi = carregar_wsgi(ambiente)
    assert wsgi.application is not ambiente.jovi

    assert sys.path == path_antes
    assert sys.modules["app"] is app_do_jovi
    assert all(sys.modules.get(nome) is mod for nome, mod in modulos_antes.items())
    novos_da_pasta_salas = {
        nome for nome, mod in sys.modules.items()
        if nome not in modulos_antes
        and os.path.abspath(getattr(mod, "__file__", None) or "/").startswith(RAIZ + os.sep)
    }
    assert novos_da_pasta_salas == {NOME_MODULO}
    assert os.path.abspath(sys.modules[NOME_MODULO].__file__) == APP_PY
    assert sys.modules[NOME_MODULO].app.root_path == RAIZ  # templates/ e static/ certos


JOVI_FLASK_APP = """\
from flask import Flask
app = Flask(__name__)

@app.route("/", defaults={"p": ""})
@app.route("/<path:p>")
def tudo(p):
    import app as modulo_app  # import tardio de um módulo do PRÓPRIO JOVI chamado "app"
    return modulo_app.QUEM
"""

SCRIPT_PROCESSO_LIMPO = """\
import importlib.util, json, os, sys
arquivo_wsgi, raiz_salas, prefixo = sys.argv[1:4]
spec = importlib.util.spec_from_file_location("uwsgi_file_jovi_conecta", arquivo_wsgi)
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)
from werkzeug.test import Client
c = Client(modulo.application)
pagina = c.get(prefixo)
print(json.dumps({
    "jovi": c.get("/qualquer/coisa").get_data(as_text=True),
    "pagina": pagina.status_code,
    "titulo": "Meeting Room Booking" in pagina.get_data(as_text=True),
    "api": c.get(prefixo + "/api/reservas").status_code,
    "raiz_no_sys_path": any(os.path.abspath(p or os.getcwd()) == raiz_salas for p in sys.path),
    "app": os.path.abspath(sys.modules["app"].__file__),
    "salas": os.path.abspath(sys.modules["salas_jovi_app"].__file__),
    "drive_service_visivel": importlib.util.find_spec("drive_service") is not None,
}))
"""


def test_processo_limpo_como_no_pythonanywhere(tmp_path):
    """Processo novo: o JOVI tem seu próprio app.py e importa "app" só durante a requisição.
    Se o bloco pusesse a pasta das salas no sys.path, esse import pegaria o app.py errado."""
    pasta_jovi = tmp_path / "mysite"
    pasta_jovi.mkdir()
    (pasta_jovi / "flask_app.py").write_text(JOVI_FLASK_APP, encoding="utf-8")
    (pasta_jovi / "app.py").write_text("QUEM = 'jovi:app.py'\n", encoding="utf-8")

    cabecalho = (
        "import sys\n"
        f"path = {str(pasta_jovi)!r}\n"
        "if path not in sys.path:\n"
        "    sys.path.append(path)\n"
        "from flask_app import app as application  # noqa\n"
    )
    arquivo_senha = tmp_path / ".salas_jovi_senha"
    arquivo_senha.write_text(SENHA + "\n", encoding="utf-8")
    bloco = (ler_bloco().replace(TEXTO_TOKEN, TOKEN).replace(CAMINHO_NO_PA, APP_PY)
             .replace(CAMINHO_SENHA_NO_PA, str(arquivo_senha)))
    arquivo_wsgi = tmp_path / "www_joviconectasp_com_br_wsgi.py"
    arquivo_wsgi.write_text(cabecalho + "\n" + bloco, encoding="utf-8")

    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["SALAS_RESERVAS_DB"] = str(tmp_path / "db" / "reservas.db")
    saida = subprocess.run(
        [sys.executable, "-c", SCRIPT_PROCESSO_LIMPO, str(arquivo_wsgi), RAIZ, PREFIXO],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=60,
    )
    assert saida.returncode == 0, saida.stderr
    r = json.loads(saida.stdout.strip().splitlines()[-1])
    assert r == {
        "jovi": "jovi:app.py",
        "pagina": 200,
        "titulo": True,
        "api": 200,
        "raiz_no_sys_path": False,
        "app": str(pasta_jovi / "app.py"),
        "salas": APP_PY,
        "drive_service_visivel": False,
    }
    assert "[salas-jovi] app de salas montado" in saida.stderr
    assert TOKEN not in saida.stderr and SENHA not in saida.stderr
