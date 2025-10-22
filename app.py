from flask import Flask, render_template, jsonify, request
from drive_service import upload_file, download_file
import json
import os

app = Flask(__name__)

# ===========================
#  CONFIG
# ===========================
DRIVE_FILE_ID = "1Q6t5qscjyI_4hQVAx1NF5bhku9QK1aLB"  # ID do arquivo no Drive
LOCAL_TEMP_FILE = os.path.join("data", "reservas_temp.json")
ADMIN_PASSWORD = "JOVI2025!"  # senha admin


# ===========================
#  FUNÇÕES DE DADOS
# ===========================
def garantir_arquivo_local():
    """Garante que a pasta e o arquivo existam."""
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(LOCAL_TEMP_FILE):
        with open(LOCAL_TEMP_FILE, "w", encoding="utf-8") as f:
            json.dump({"reservas": []}, f, ensure_ascii=False, indent=2)
    return LOCAL_TEMP_FILE


def load_data():
    """Tenta baixar do Drive, se falhar usa local."""
    garantir_arquivo_local()

    try:
        # tenta atualizar o local com o Drive
        download_file(DRIVE_FILE_ID, LOCAL_TEMP_FILE)
        print("☁️ Dados baixados do Drive.")
    except Exception as e:
        print(f"⚠️ Falha ao baixar do Drive: {e}")

    try:
        with open(LOCAL_TEMP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "reservas" not in data:
                data = {"reservas": []}
            return data
    except Exception as e:
        print(f"⚠️ Erro ao ler JSON: {e}")
        return {"reservas": []}


def save_data(data):
    """Salva localmente e tenta enviar pro Drive."""
    garantir_arquivo_local()

    if "reservas" not in data:
        data["reservas"] = []

    with open(LOCAL_TEMP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"💾 {len(data['reservas'])} reservas salvas localmente.")

    # tenta enviar pro Drive em background
    try:
        upload_file(LOCAL_TEMP_FILE, DRIVE_FILE_ID)
        print("✅ Arquivo sincronizado com o Google Drive.")
    except Exception as e:
        print(f"⚠️ Falha ao sincronizar Drive: {e}")


# ===========================
#  ROTAS
# ===========================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/reservas", methods=["GET"])
def get_reservas():
    data = load_data()
    print(f"📤 Retornando {len(data['reservas'])} reservas.")
    return jsonify(data)


@app.route("/api/reservas", methods=["POST"])
def add_reserva():
    """Adiciona novas reservas e salva local/Drive."""
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON"}), 400

    data = load_data()

    if isinstance(payload, list):
        data["reservas"].extend(payload)
    else:
        data["reservas"].append(payload)

    save_data(data)
    print("📥 Reserva(s) adicionada(s) com sucesso.")
    return jsonify({"status": "ok"}), 201


@app.route("/api/reservas/delete", methods=["POST"])
def delete_reserva():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid request"}), 400

    senha = payload.get("senha")
    id_ref = payload.get("id")

    if senha != ADMIN_PASSWORD:
        return jsonify({"error": "Incorrect password"}), 403

    data = load_data()
    antes = len(data["reservas"])
    data["reservas"] = [
        r for r in data["reservas"]
        if r.get("idRepeticao") != id_ref and r.get("data") != id_ref
    ]
    depois = len(data["reservas"])

    save_data(data)
    print(f"🗑️ {antes - depois} reserva(s) removida(s).")
    return jsonify({"message": "Reservation deleted"}), 200


# ===========================
#  EXECUÇÃO
# ===========================
if __name__ == "__main__":
    app.run(debug=True)
