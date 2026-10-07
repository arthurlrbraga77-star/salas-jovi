from flask import Flask, render_template, jsonify, request
from contextlib import closing
import datetime
import hmac
import math
import os
import re
import sqlite3
import uuid

app = Flask(__name__)

# ===========================
#  CONFIGURAÇÕES GERAIS
# ===========================
# Todos os caminhos são absolutos, a partir da pasta deste arquivo:
# no PythonAnywhere o diretório de trabalho do WSGI NÃO é a pasta do projeto.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PADRAO = os.path.join(BASE_DIR, "data", "reservas.db")

# A senha de admin vem SOMENTE da variável de ambiente ADMIN_PASSWORD
# (lida a cada requisição). Se não estiver definida, o cancelamento fica desativado.

MAX_ITENS_POR_POST = 5000       # repetição semanal até 2030 x 8 slots ≈ 2300 itens
MAX_TAMANHO_TEXTO = 200         # limite para nome, email, sala e idRepeticao
MAX_DURACAO_HORAS = 24
MAX_CONFLITOS_NA_MENSAGEM = 5
TIMEOUT_DB_SEGUNDOS = 15        # espera pelo lock do SQLite (vários workers)
LOTE_SQL = 500                  # itens por consulta "IN (...)"

REGEX_DATA_HORA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}")
REGEX_DIA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# Limite do corpo da requisição (5000 itens cabem com folga)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


# ===========================
#  BANCO DE DADOS (SQLITE)
# ===========================
SQL_CRIAR_TABELA = """
CREATE TABLE IF NOT EXISTS reservas (
    id INTEGER PRIMARY KEY,
    sala TEXT NOT NULL,
    data TEXT NOT NULL,            -- 'YYYY-MM-DDTHH:MM' (horário local), um slot de 30 min
    nome TEXT NOT NULL,
    email TEXT NOT NULL,
    duracao REAL NOT NULL,         -- duração da reserva inteira, em horas
    id_repeticao TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Um slot (sala + data) só pode ter uma reserva: o próprio banco garante isso
CREATE UNIQUE INDEX IF NOT EXISTS idx_reservas_sala_data ON reservas (sala, data);
CREATE INDEX IF NOT EXISTS idx_reservas_data ON reservas (data);
CREATE INDEX IF NOT EXISTS idx_reservas_id_repeticao ON reservas (id_repeticao);
"""


def caminho_db():
    """Caminho absoluto do banco. Lido a cada chamada (testes e WSGI podem trocar)."""
    caminho = os.environ.get("RESERVAS_DB", "").strip() or DB_PADRAO
    if not os.path.isabs(caminho):
        caminho = os.path.join(BASE_DIR, caminho)
    return caminho


def conectar():
    """Abre uma conexão nova (uma por requisição) e garante pasta e tabela."""
    caminho = caminho_db()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)

    # isolation_level=None: nós controlamos as transações (BEGIN IMMEDIATE / COMMIT).
    # Usamos o journal padrão do SQLite (não WAL): o disco do PythonAnywhere é de rede
    # e o WAL depende de memória compartilhada. O timeout faz um worker esperar o
    # outro em vez de falhar com "database is locked".
    conn = sqlite3.connect(caminho, timeout=TIMEOUT_DB_SEGUNDOS, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {TIMEOUT_DB_SEGUNDOS * 1000}")
    conn.executescript(SQL_CRIAR_TABELA)
    return conn


def desfazer(conn):
    """Faz ROLLBACK se houver transação aberta."""
    if conn.in_transaction:
        conn.execute("ROLLBACK")


def linha_para_json(linha):
    """Converte uma linha do banco para o formato que o front-end usa."""
    return {
        "data": linha["data"],
        "nome": linha["nome"],
        "email": linha["email"],
        "duracao": linha["duracao"],
        "idRepeticao": linha["id_repeticao"],
        "sala": linha["sala"],
    }


# ===========================
#  FUNÇÕES DE SUPORTE
# ===========================
def erro(mensagem, status, **extra):
    """Resposta de erro em JSON: {"error": "..."}."""
    corpo = {"error": mensagem}
    corpo.update(extra)
    return jsonify(corpo), status


def ler_dia(texto):
    """Converte 'YYYY-MM-DD' em date. Retorna None se for inválido."""
    if not REGEX_DIA.fullmatch(texto):
        return None
    try:
        return datetime.datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def data_hora_valida(texto):
    """True se o texto for 'YYYY-MM-DDTHH:MM' e uma data/hora real."""
    if not isinstance(texto, str) or not REGEX_DATA_HORA.fullmatch(texto):
        return False
    try:
        datetime.datetime.strptime(texto, "%Y-%m-%dT%H:%M")
        return True
    except ValueError:
        return False


def texto_obrigatorio(item, campo):
    """Lê um campo de texto obrigatório (com trim). Retorna (valor, erro)."""
    valor = item.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        return None, f"'{campo}' is required and must be a non-empty string"
    valor = valor.strip()
    if len(valor) > MAX_TAMANHO_TEXTO:
        return None, f"'{campo}' must be at most {MAX_TAMANHO_TEXTO} characters"
    return valor, None


def validar_reserva(item, id_padrao):
    """Valida e normaliza um item recebido. Retorna (reserva, erro)."""
    if not isinstance(item, dict):
        return None, "each reservation must be a JSON object"

    data = item.get("data")
    if not data_hora_valida(data):
        return None, "'data' must be a valid date/time in the format YYYY-MM-DDTHH:MM"

    nome, msg = texto_obrigatorio(item, "nome")
    if msg:
        return None, msg
    email, msg = texto_obrigatorio(item, "email")
    if msg:
        return None, msg
    sala, msg = texto_obrigatorio(item, "sala")
    if msg:
        return None, msg

    # idRepeticao é opcional: se faltar, todos os itens desta requisição
    # sem id compartilham o mesmo uuid (são um único agendamento)
    id_repeticao = item.get("idRepeticao")
    if id_repeticao is None or (isinstance(id_repeticao, str) and not id_repeticao.strip()):
        id_repeticao = id_padrao
    elif not isinstance(id_repeticao, str):
        return None, "'idRepeticao' must be a string"
    else:
        id_repeticao = id_repeticao.strip()
        if len(id_repeticao) > MAX_TAMANHO_TEXTO:
            return None, f"'idRepeticao' must be at most {MAX_TAMANHO_TEXTO} characters"

    duracao = item.get("duracao")
    if (isinstance(duracao, bool) or not isinstance(duracao, (int, float))
            or not math.isfinite(duracao) or not 0 < duracao <= MAX_DURACAO_HORAS):
        return None, f"'duracao' must be a number of hours greater than 0 and at most {MAX_DURACAO_HORAS}"

    return {
        "sala": sala,
        "data": data,
        "nome": nome,
        "email": email,
        "duracao": float(duracao),
        "id_repeticao": id_repeticao,
    }, None


def formatar_slots(slots):
    """Texto curto com até MAX_CONFLITOS_NA_MENSAGEM horários: '2030-01-07 08:00, ...'."""
    mostrar = [data.replace("T", " ") for _, data in slots[:MAX_CONFLITOS_NA_MENSAGEM]]
    texto = ", ".join(mostrar)
    if len(slots) > MAX_CONFLITOS_NA_MENSAGEM:
        texto += f" (+{len(slots) - MAX_CONFLITOS_NA_MENSAGEM} more)"
    return texto


def buscar_conflitos(conn, reservas):
    """Retorna a lista ordenada de (sala, data) que já estão ocupados no banco."""
    por_sala = {}
    for r in reservas:
        por_sala.setdefault(r["sala"], []).append(r["data"])

    conflitos = []
    for sala, datas in por_sala.items():
        for i in range(0, len(datas), LOTE_SQL):
            lote = datas[i:i + LOTE_SQL]
            marcadores = ",".join("?" * len(lote))
            linhas = conn.execute(
                f"SELECT sala, data FROM reservas WHERE sala = ? AND data IN ({marcadores})",
                [sala, *lote],
            ).fetchall()
            conflitos.extend((linha["sala"], linha["data"]) for linha in linhas)
    return sorted(conflitos, key=lambda c: (c[1], c[0]))


# ===========================
#  ROTAS DO SISTEMA
# ===========================
@app.route("/")
def index():
    """Página principal."""
    return render_template("index.html")


@app.route("/api/reservas", methods=["GET"])
def get_reservas():
    """
    Retorna as reservas. Filtros opcionais (sem filtros = todas):
      inicio=YYYY-MM-DD  -> a partir deste dia (inclusivo)
      fim=YYYY-MM-DD     -> até este dia (INCLUSIVO, o dia inteiro)
      sala=<nome>        -> só esta sala
    """
    inicio_txt = request.args.get("inicio", "").strip()
    fim_txt = request.args.get("fim", "").strip()
    sala = request.args.get("sala", "").strip()

    condicoes, params = [], []
    inicio = fim = None

    if inicio_txt:
        inicio = ler_dia(inicio_txt)
        if inicio is None:
            return erro("Invalid 'inicio': expected a date in the format YYYY-MM-DD", 400)
        condicoes.append("data >= ?")
        params.append(inicio.isoformat())

    if fim_txt:
        fim = ler_dia(fim_txt)
        if fim is None:
            return erro("Invalid 'fim': expected a date in the format YYYY-MM-DD", 400)
        # 'fim' é inclusivo: pega tudo antes do dia seguinte
        if fim < datetime.date.max:
            condicoes.append("data < ?")
            params.append((fim + datetime.timedelta(days=1)).isoformat())

    if inicio and fim and inicio > fim:
        return erro("'inicio' must be on or before 'fim'", 400)

    if sala:
        condicoes.append("sala = ?")
        params.append(sala)

    sql = "SELECT sala, data, nome, email, duracao, id_repeticao FROM reservas"
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY data, sala, id"

    with closing(conectar()) as conn:
        linhas = conn.execute(sql, params).fetchall()

    return jsonify({"reservas": [linha_para_json(linha) for linha in linhas]})


@app.route("/api/reservas", methods=["POST"])
def add_reserva():
    """Adiciona uma reserva (objeto) ou várias (lista). Tudo ou nada."""
    payload = request.get_json(silent=True)
    if payload is None:
        return erro("Invalid JSON", 400)

    itens = payload if isinstance(payload, list) else [payload]
    if not isinstance(payload, (list, dict)) or not itens:
        return erro("Expected a reservation object or a non-empty list of reservations", 400)
    if len(itens) > MAX_ITENS_POR_POST:
        return erro(f"Too many reservations in one request (max {MAX_ITENS_POR_POST})", 400)

    # 1) Valida todos os itens antes de tocar no banco
    id_padrao = str(uuid.uuid4())
    novas = []
    for posicao, item in enumerate(itens, start=1):
        reserva, msg = validar_reserva(item, id_padrao)
        if msg:
            prefixo = f"Reservation #{posicao}: " if len(itens) > 1 else ""
            return erro(f"Invalid reservation. {prefixo}{msg}", 400)
        novas.append(reserva)

    # 2) Horários repetidos dentro da própria requisição
    vistos, repetidos = set(), set()
    for r in novas:
        chave = (r["sala"], r["data"])
        if chave in vistos:
            repetidos.add(chave)
        vistos.add(chave)
    if repetidos:
        repetidos = sorted(repetidos, key=lambda c: (c[1], c[0]))
        return erro(
            "The request contains the same time slot more than once: " + formatar_slots(repetidos),
            409,
            conflicts=[d for _, d in repetidos[:MAX_CONFLITOS_NA_MENSAGEM]],
        )

    # 3) Checa conflitos e insere numa única transação.
    #    BEGIN IMMEDIATE trava a escrita: outro worker espera até terminarmos,
    #    então "checar + inserir" é atômico. O índice UNIQUE é a última garantia.
    with closing(conectar()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conflitos = buscar_conflitos(conn, novas)
            if conflitos:
                desfazer(conn)
                return erro(
                    "Time slot already booked: " + formatar_slots(conflitos),
                    409,
                    conflicts=[d for _, d in conflitos[:MAX_CONFLITOS_NA_MENSAGEM]],
                )
            conn.executemany(
                "INSERT INTO reservas (sala, data, nome, email, duracao, id_repeticao) "
                "VALUES (:sala, :data, :nome, :email, :duracao, :id_repeticao)",
                novas,
            )
            conn.execute("COMMIT")
        except sqlite3.IntegrityError:
            desfazer(conn)
            return erro("Time slot already booked", 409)
        except sqlite3.OperationalError as e:
            desfazer(conn)
            print(f"[reservas] Erro no banco ao salvar: {e}")
            return erro("The server is busy, please try again", 503)
        except Exception:
            desfazer(conn)
            raise

    print(f"[reservas] {len(novas)} reserva(s) adicionada(s).")
    return jsonify({"status": "ok", "count": len(novas)}), 201


@app.route("/api/reservas/delete", methods=["POST"])
def delete_reserva():
    """Remove uma reserva (ou toda a série repetida) com senha administrativa."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return erro("Invalid request", 400)

    senha_admin = os.environ.get("ADMIN_PASSWORD", "")
    if not senha_admin:
        return erro("Admin password not configured on the server", 503)

    senha = payload.get("senha")
    if not isinstance(senha, str) or not hmac.compare_digest(
            senha.encode("utf-8"), senha_admin.encode("utf-8")):
        return erro("Incorrect password", 403)

    id_ref = payload.get("id")
    if not isinstance(id_ref, str) or not id_ref.strip():
        return erro("Missing reservation id", 400)
    id_ref = id_ref.strip()

    # Mesma regra de antes: apaga pelo idRepeticao ou, se o id for uma data, pela data
    condicao, params = "id_repeticao = ?", [id_ref]
    if REGEX_DATA_HORA.fullmatch(id_ref):
        condicao, params = "(id_repeticao = ? OR data = ?)", [id_ref, id_ref]

    # Opcional: limita à sala informada
    sala = payload.get("sala")
    if isinstance(sala, str) and sala.strip():
        condicao += " AND sala = ?"
        params.append(sala.strip())

    with closing(conectar()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            apagadas = conn.execute(f"DELETE FROM reservas WHERE {condicao}", params).rowcount
            conn.execute("COMMIT")
        except sqlite3.OperationalError as e:
            desfazer(conn)
            print(f"[reservas] Erro no banco ao apagar: {e}")
            return erro("The server is busy, please try again", 503)
        except Exception:
            desfazer(conn)
            raise

    if apagadas == 0:
        return erro("Reservation not found", 404)

    print(f"[reservas] {apagadas} reserva(s) removida(s).")
    return jsonify({"message": "Reservation deleted", "deleted": apagadas}), 200


@app.errorhandler(413)
def corpo_grande_demais(_e):
    """Requisição maior que MAX_CONTENT_LENGTH."""
    return erro("Request too large", 413)


# ===========================
#  EXECUÇÃO LOCAL (DEV)
# ===========================
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
