# Redirecionamento da hospedagem antiga (QR code impresso antigo -> endereço novo)
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402

DESTINO = "https://www.joviconectasp.com.br/salas/token-de-teste-1234567890/"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SALAS_RESERVAS_DB", str(tmp_path / "r.db"))
    monkeypatch.delenv("SALAS_REDIRECT_URL", raising=False)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.mark.parametrize("caminho", ["/", "/api/reservas", "/static/style.css", "/qualquer"])
def test_redireciona_tudo_quando_configurado(client, monkeypatch, caminho):
    monkeypatch.setenv("SALAS_REDIRECT_URL", DESTINO)
    res = client.get(caminho)
    assert res.status_code == 302
    assert res.headers["Location"] == DESTINO
    assert res.headers["Referrer-Policy"] == "no-referrer"


def test_sem_variavel_funciona_normal(client):
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("valor", ["", "   ", "http://inseguro.example/", "javascript:alert(1)", "/relativo"])
def test_valor_invalido_nao_redireciona(client, monkeypatch, valor):
    monkeypatch.setenv("SALAS_REDIRECT_URL", valor)
    assert client.get("/").status_code == 200
