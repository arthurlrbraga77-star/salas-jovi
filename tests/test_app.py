# ===========================
#  TESTES DA API DE RESERVAS
# ===========================
# Rodar com:  python3 -m pytest -q tests
import os
import subprocess
import sys
import threading

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import app as app_module  # noqa: E402

SENHA = "senha-de-teste"


# ===========================
#  FIXTURES E AJUDANTES
# ===========================
@pytest.fixture
def db_path(tmp_path, monkeypatch):
    caminho = tmp_path / "sub" / "reservas.db"  # pasta ainda não existe
    monkeypatch.setenv("RESERVAS_DB", str(caminho))
    monkeypatch.setenv("ADMIN_PASSWORD", SENHA)
    return caminho


@pytest.fixture
def client(db_path):
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def reserva(data="2030-01-07T08:00", sala="samba", **extra):
    item = {
        "data": data,
        "nome": "Sales Meeting",
        "email": "a@jovimobile.com",
        "duracao": 1,
        "idRepeticao": "rep-1",
        "sala": sala,
    }
    item.update(extra)
    return item


def todas(client, **params):
    res = client.get("/api/reservas", query_string=params)
    assert res.status_code == 200
    return res.get_json()["reservas"]


def apagar(client, **corpo):
    return client.post("/api/reservas/delete", json=corpo)


# ===========================
#  CONFIGURAÇÃO / BANCO
# ===========================
def test_get_vazio_cria_pasta_e_banco(client, db_path):
    assert not db_path.parent.exists()
    res = client.get("/api/reservas")
    assert res.status_code == 200
    assert res.get_json() == {"reservas": []}
    assert db_path.exists()


def test_caminho_padrao_absoluto(monkeypatch):
    monkeypatch.delenv("RESERVAS_DB", raising=False)
    esperado = os.path.join(os.path.dirname(os.path.abspath(app_module.__file__)), "data", "reservas.db")
    assert app_module.caminho_db() == esperado
    assert os.path.isabs(app_module.caminho_db())


def test_caminho_relativo_vira_absoluto(monkeypatch):
    monkeypatch.setenv("RESERVAS_DB", "outra/reservas.db")
    assert app_module.caminho_db() == os.path.join(app_module.BASE_DIR, "outra", "reservas.db")


def test_sem_google_drive_e_sem_senha_fixa():
    assert "drive_service" not in sys.modules
    assert not any(m.startswith("google") for m in sys.modules)
    with open(os.path.join(RAIZ, "app.py"), encoding="utf-8") as f:
        fonte = f.read()
    assert "JOVI2025!" not in fonte
    assert "drive_service" not in fonte


def test_pagina_principal(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Meeting Room Booking" in res.data


# ===========================
#  POST
# ===========================
def test_post_unico(client):
    res = client.post("/api/reservas", json=reserva())
    assert res.status_code == 201
    assert res.get_json() == {"status": "ok", "count": 1}
    assert todas(client) == [{
        "data": "2030-01-07T08:00",
        "nome": "Sales Meeting",
        "email": "a@jovimobile.com",
        "duracao": 1.0,
        "idRepeticao": "rep-1",
        "sala": "samba",
    }]


def test_post_lista(client):
    itens = [reserva(data=f"2030-01-07T{h}") for h in ("08:00", "08:30", "09:00")]
    res = client.post("/api/reservas", json=itens)
    assert res.status_code == 201
    assert res.get_json()["count"] == 3
    assert [r["data"] for r in todas(client)] == ["2030-01-07T08:00", "2030-01-07T08:30", "2030-01-07T09:00"]


def test_post_faz_trim_e_gera_id_repeticao(client):
    itens = [
        reserva(data="2030-01-07T08:00", nome="  Daily  ", email=" x@y.com "),
        reserva(data="2030-01-07T08:30"),
    ]
    for item in itens:
        del item["idRepeticao"]
    assert client.post("/api/reservas", json=itens).status_code == 201
    lista = todas(client)
    assert lista[0]["nome"] == "Daily" and lista[0]["email"] == "x@y.com"
    # sem idRepeticao: a requisição inteira vira um único agendamento
    assert lista[0]["idRepeticao"] == lista[1]["idRepeticao"]
    assert len(lista[0]["idRepeticao"]) == 36


def test_post_lista_grande_repeticao_semanal(client):
    # ~ 5 anos de repetição semanal x 8 slots
    import datetime
    base = datetime.datetime(2026, 1, 5, 8, 0)
    itens = []
    for semana in range(260):
        for slot in range(8):
            d = base + datetime.timedelta(weeks=semana, minutes=30 * slot)
            itens.append(reserva(data=d.strftime("%Y-%m-%dT%H:%M"), duracao=4))
    res = client.post("/api/reservas", json=itens)
    assert res.status_code == 201
    assert res.get_json()["count"] == 2080


# ===========================
#  GET COM FILTROS
# ===========================
def test_get_filtros(client):
    itens = [
        reserva(data="2030-01-06T17:00"),                 # domingo antes
        reserva(data="2030-01-07T08:00"),                 # segunda
        reserva(data="2030-01-11T18:00"),                 # sexta (fim, inclusivo)
        reserva(data="2030-01-12T08:00"),                 # sábado depois
        reserva(data="2030-01-08T10:00", sala="outra"),   # outra sala
    ]
    assert client.post("/api/reservas", json=itens).status_code == 201

    # sem filtros: tudo (compatível com a versão antiga)
    assert len(todas(client)) == 5

    semana = todas(client, inicio="2030-01-07", fim="2030-01-11")
    assert [r["data"] for r in semana] == ["2030-01-07T08:00", "2030-01-08T10:00", "2030-01-11T18:00"]

    semana_samba = todas(client, inicio="2030-01-07", fim="2030-01-11", sala="samba")
    assert [r["data"] for r in semana_samba] == ["2030-01-07T08:00", "2030-01-11T18:00"]

    assert [r["data"] for r in todas(client, inicio="2030-01-11")] == ["2030-01-11T18:00", "2030-01-12T08:00"]
    assert [r["data"] for r in todas(client, fim="2030-01-06")] == ["2030-01-06T17:00"]
    assert [r["data"] for r in todas(client, inicio="2030-01-07", fim="2030-01-07")] == ["2030-01-07T08:00"]
    assert [r["sala"] for r in todas(client, sala="outra")] == ["outra"]
    assert todas(client, sala="inexistente") == []


@pytest.mark.parametrize("params", [
    {"inicio": "07/01/2030"},
    {"fim": "2030-13-01"},
    {"inicio": "2030-01-07T08:00"},
    {"inicio": "2030-01-10", "fim": "2030-01-07"},
])
def test_get_filtro_invalido(client, params):
    res = client.get("/api/reservas", query_string=params)
    assert res.status_code == 400
    assert "error" in res.get_json()


# ===========================
#  VALIDAÇÃO (400)
# ===========================
@pytest.mark.parametrize("item", [
    reserva(data="2030-01-07 08:00"),
    reserva(data="2030-01-07T08:00:00"),
    reserva(data="2030-02-30T08:00"),
    reserva(data="2030-01-07T25:00"),
    reserva(data=None),
    reserva(nome=""),
    reserva(nome="   "),
    reserva(nome=123),
    reserva(email=None),
    reserva(nome="x" * 201),
    reserva(sala=""),
    reserva(sala=None),
    reserva(idRepeticao=42),
    reserva(duracao="1"),
    reserva(duracao=True),
    reserva(duracao=0),
    reserva(duracao=-1),
    reserva(duracao=None),
])
def test_post_item_invalido(client, item):
    res = client.post("/api/reservas", json=item)
    assert res.status_code == 400
    assert res.get_json()["error"].startswith("Invalid reservation")
    assert todas(client) == []


def test_post_lista_com_um_item_invalido_nao_salva_nada(client):
    itens = [reserva(data="2030-01-07T08:00"), reserva(data="2030-01-07T08:30", email="")]
    res = client.post("/api/reservas", json=itens)
    assert res.status_code == 400
    assert "Reservation #2" in res.get_json()["error"]
    assert todas(client) == []


@pytest.mark.parametrize("corpo", ["nao e json", "[]", "null", "5", '"texto"', "[1, 2]"])
def test_post_corpo_invalido(client, corpo):
    res = client.post("/api/reservas", data=corpo, content_type="application/json")
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_post_lista_grande_demais(client):
    itens = [reserva(data="2030-01-07T08:00")] * (app_module.MAX_ITENS_POR_POST + 1)
    res = client.post("/api/reservas", json=itens)
    assert res.status_code == 400
    assert "Too many" in res.get_json()["error"]


# ===========================
#  CONFLITOS (409)
# ===========================
def test_conflito_com_reserva_existente(client):
    assert client.post("/api/reservas", json=reserva(data="2030-01-07T09:00")).status_code == 201
    res = client.post("/api/reservas", json=reserva(data="2030-01-07T09:00", nome="Outra", idRepeticao="rep-2"))
    assert res.status_code == 409
    corpo = res.get_json()
    assert "already booked" in corpo["error"]
    assert "2030-01-07 09:00" in corpo["error"]
    assert len(todas(client)) == 1


def test_conflito_tudo_ou_nada(client):
    assert client.post("/api/reservas", json=reserva(data="2030-01-07T09:00")).status_code == 201
    itens = [reserva(data=f"2030-01-07T{h}", idRepeticao="rep-2") for h in ("08:00", "08:30", "09:00", "09:30")]
    res = client.post("/api/reservas", json=itens)
    assert res.status_code == 409
    # nenhum dos horários livres foi gravado
    assert [r["data"] for r in todas(client)] == ["2030-01-07T09:00"]


def test_conflito_duplicado_no_proprio_payload(client):
    itens = [reserva(data="2030-01-07T08:00"), reserva(data="2030-01-07T08:30"), reserva(data="2030-01-07T08:00")]
    res = client.post("/api/reservas", json=itens)
    assert res.status_code == 409
    assert "2030-01-07 08:00" in res.get_json()["error"]
    assert todas(client) == []


def test_mesmo_horario_em_outra_sala_nao_conflita(client):
    assert client.post("/api/reservas", json=reserva(sala="samba")).status_code == 201
    assert client.post("/api/reservas", json=reserva(sala="outra")).status_code == 201
    assert len(todas(client)) == 2


def test_mensagem_de_conflito_lista_no_maximo_cinco(client):
    itens = [reserva(data=f"2030-01-{d:02d}T08:00") for d in range(1, 11)]
    assert client.post("/api/reservas", json=itens).status_code == 201
    res = client.post("/api/reservas", json=[dict(i, idRepeticao="rep-2") for i in itens])
    assert res.status_code == 409
    corpo = res.get_json()
    assert "(+5 more)" in corpo["error"]
    assert len(corpo["conflicts"]) == 5


def test_conflito_concorrente_entre_threads(client):
    """Várias requisições ao mesmo tempo pelo mesmo horário: só uma pode ganhar."""
    barreira = threading.Barrier(8)
    status = []

    def tentar(n):
        with app_module.app.test_client() as c:
            barreira.wait()
            itens = [reserva(data=f"2030-01-07T{h}", idRepeticao=f"t{n}") for h in ("08:00", "08:30", "09:00")]
            status.append(c.post("/api/reservas", json=itens).status_code)

    threads = [threading.Thread(target=tentar, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(status) == [201] + [409] * 7
    assert len({r["idRepeticao"] for r in todas(client)}) == 1
    assert len(todas(client)) == 3


def test_conflito_concorrente_entre_processos(client, db_path):
    """Simula vários workers (processos) do PythonAnywhere gravando no mesmo banco."""
    client.get("/api/reservas")  # cria o banco
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); import app\n"
        "itens = [dict(data='2030-03-%02dT%s' % (d, h), nome='p', email='e', duracao=1,"
        " idRepeticao=sys.argv[2], sala='samba') for d in range(1, 29) for h in ('08:00', '08:30')]\n"
        "print(app.app.test_client().post('/api/reservas', json=itens).status_code)\n"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", script, RAIZ, f"p{n}"], stdout=subprocess.PIPE,
                         env=dict(os.environ, RESERVAS_DB=str(db_path)), text=True)
        for n in range(4)
    ]
    # a última linha da saída é o status HTTP (antes pode vir o log do app)
    status = sorted(int(p.communicate(timeout=60)[0].strip().splitlines()[-1]) for p in procs)
    assert status == [201, 409, 409, 409]
    assert len(todas(client)) == 56


# ===========================
#  DELETE
# ===========================
def test_delete_por_id_repeticao(client):
    itens = [reserva(data=f"2030-01-{d:02d}T08:00", idRepeticao="serie") for d in (7, 14, 21)]
    assert client.post("/api/reservas", json=itens).status_code == 201
    assert client.post("/api/reservas", json=reserva(data="2030-01-08T08:00", idRepeticao="outra")).status_code == 201

    res = apagar(client, id="serie", senha=SENHA)
    assert res.status_code == 200
    assert res.get_json() == {"message": "Reservation deleted", "deleted": 3}
    assert [r["idRepeticao"] for r in todas(client)] == ["outra"]


def test_delete_por_data(client):
    assert client.post("/api/reservas", json=reserva(data="2030-01-07T08:00")).status_code == 201
    assert client.post("/api/reservas", json=reserva(data="2030-01-07T08:30", idRepeticao="x")).status_code == 201
    res = apagar(client, id="2030-01-07T08:00", senha=SENHA)
    assert res.status_code == 200
    assert res.get_json()["deleted"] == 1
    assert [r["data"] for r in todas(client)] == ["2030-01-07T08:30"]


def test_delete_respeita_sala_quando_informada(client):
    assert client.post("/api/reservas", json=reserva(sala="samba", idRepeticao="a")).status_code == 201
    assert client.post("/api/reservas", json=reserva(sala="outra", idRepeticao="b")).status_code == 201
    res = apagar(client, id="2030-01-07T08:00", senha=SENHA, sala="samba")
    assert res.get_json()["deleted"] == 1
    assert [r["sala"] for r in todas(client)] == ["outra"]


def test_delete_senha_errada(client):
    assert client.post("/api/reservas", json=reserva()).status_code == 201
    for senha in ("errada", "", None, 123, "JOVI2025!", "sénha"):
        res = apagar(client, id="rep-1", senha=senha)
        assert res.status_code == 403
        assert res.get_json() == {"error": "Incorrect password"}
    assert len(todas(client)) == 1


@pytest.mark.parametrize("valor", [None, ""])
def test_delete_sem_admin_password_configurada(client, monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("ADMIN_PASSWORD", valor)
    assert client.post("/api/reservas", json=reserva()).status_code == 201
    res = apagar(client, id="rep-1", senha="")
    assert res.status_code == 503
    assert res.get_json() == {"error": "Admin password not configured on the server"}
    assert len(todas(client)) == 1


@pytest.mark.parametrize("corpo", [{}, {"id": ""}, {"id": "   "}, {"id": None}, {"id": 5}])
def test_delete_sem_id(client, corpo):
    assert client.post("/api/reservas", json=reserva()).status_code == 201
    res = apagar(client, senha=SENHA, **corpo)
    assert res.status_code == 400
    assert len(todas(client)) == 1


def test_delete_corpo_invalido(client):
    res = client.post("/api/reservas/delete", data="x", content_type="application/json")
    assert res.status_code == 400


def test_delete_nao_encontrado(client):
    assert client.post("/api/reservas", json=reserva()).status_code == 201
    res = apagar(client, id="nao-existe", senha=SENHA)
    assert res.status_code == 404
    assert res.get_json() == {"error": "Reservation not found"}
    assert len(todas(client)) == 1
