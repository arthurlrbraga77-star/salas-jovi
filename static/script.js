// ===============================
//  CONFIGURAÇÕES GERAIS
// ===============================
let currentDate = new Date();
let reservas = [];

const horas = [
  "08:00", "08:30", "09:00", "09:30", "10:00", "10:30",
  "11:00", "11:30", "12:00", "12:30", "13:00", "13:30",
  "14:00", "14:30", "15:00", "15:30", "16:00", "16:30",
  "17:00", "17:30", "18:00"
];

// ===============================
//  FUNÇÕES UTILITÁRIAS
// ===============================
function ymd(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function localISO(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function inicioDaSemana(date) {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const day = d.getDay();
  const diff = (day === 0 ? -6 : 1) - day;
  d.setDate(d.getDate() + diff);
  return d;
}

// ===============================
//  API (CARREGAR / SALVAR)
// ===============================
async function carregarReservas() {
  try {
    const res = await fetch("/api/reservas");
    if (!res.ok) throw new Error("Falha ao carregar reservas");
    const data = await res.json();
    reservas = data.reservas || [];
    console.log(`📥 Reservas carregadas: ${reservas.length}`);
  } catch (err) {
    console.error("❌ Erro ao carregar reservas:", err);
    reservas = [];
  }
}

async function salvarReservasServidor(novas) {
  try {
    const res = await fetch("/api/reservas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(novas)
    });

    if (!res.ok) {
      const txt = await res.text();
      console.error("❌ Erro ao salvar reserva:", txt);
      alert("Erro ao salvar reserva no servidor.");
    } else {
      console.log("✅ Reserva(s) enviada(s) ao servidor.");
    }
  } catch (err) {
    console.error("🚨 Erro grave ao salvar reservas:", err);
    alert("Falha ao comunicar com o servidor.");
  }
}

// ===============================
//  RENDERIZAÇÃO DO CALENDÁRIO
// ===============================
async function gerarCalendario() {
  await carregarReservas();

  const inicioSemana = inicioDaSemana(currentDate);
  const dias = Array.from({ length: 5 }, (_, i) => {
    const d = new Date(inicioSemana);
    d.setDate(d.getDate() + i);
    return d;
  });

  const header = document.querySelector(".grid.header");
  const body = document.querySelector(".grid.body");

  if (!header || !body) {
    console.warn("⚠️ Elementos do calendário não encontrados no HTML.");
    return;
  }

  // Cabeçalho da semana
  header.innerHTML =
    `<div>Time</div>` +
    dias
      .map(
        (d) =>
          `<div>${d.toLocaleDateString("en-US", {
            weekday: "short",
            day: "2-digit",
            month: "2-digit",
          })}</div>`
      )
      .join("");

  // Corpo da tabela
  body.innerHTML = "";
  horas.forEach((hora) => {
    const linha = document.createElement("div");
    linha.classList.add("grid");
    linha.style.gridTemplateColumns = "70px repeat(5, 1fr)";
    linha.innerHTML = `<div class="time-cell">${hora}</div>`;

    dias.forEach((dia) => {
      const slot = document.createElement("div");
      slot.classList.add("slot-cell");
      const chave = `${ymd(dia)}T${hora}`;
      const reserva = reservas.find((r) => r.data === chave);

      if (reserva) {
        slot.classList.add("busy");
        slot.textContent = reserva.nome || "Booked";
        slot.title = `${reserva.nome || "Meeting"} — ${reserva.email || ""}`;

        slot.addEventListener("click", async () => {
          const senha = prompt(
            `To cancel "${reserva.nome}", please enter the admin password:`
          );
          if (senha === null) return;

          const res = await fetch("/api/reservas/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              id: reserva.idRepeticao || reserva.data,
              senha,
            }),
          });

          const result = await res.json();
          if (res.status === 200) {
            alert("✅ Reservation successfully canceled.");
            await gerarCalendario();
          } else {
            alert(`❌ ${result.error || "Error while deleting reservation."}`);
          }
        });
      } else {
        slot.classList.add("free");
        slot.addEventListener("click", () => abrirModal(dia, hora));
      }

      linha.appendChild(slot);
    });

    body.appendChild(linha);
  });

  document.querySelector("#semanaAtual").textContent = `Week: ${
    dias[0].toLocaleDateString("en-US")
  } - ${dias[4].toLocaleDateString("en-US")}`;
}

// ===============================
//  MODAL DE RESERVA (CORRIGIDO)
// ===============================
function abrirModal(dia, hora) {
  const dlg = document.querySelector("#reservaModal");
  document.querySelector("#infoDia").textContent = `Day ${dia.toLocaleDateString(
    "en-US"
  )} at ${hora}`;
  dlg.showModal();

  // Substitui listeners antigos
  const oldConfirm = document.querySelector("#confirmar");
  const oldCancel = document.querySelector("#cancelar");
  const newConfirm = oldConfirm.cloneNode(true);
  const newCancel = oldCancel.cloneNode(true);
  oldConfirm.parentNode.replaceChild(newConfirm, oldConfirm);
  oldCancel.parentNode.replaceChild(newCancel, oldCancel);

  // Botão Confirmar
  newConfirm.onclick = async () => {
    try {
      const nome = document.querySelector("#nome").value.trim();
      const email = document.querySelector("#email").value.trim();
      const duracao = parseFloat(document.querySelector("#duracao").value);
      const repetir = document.querySelector("#repetir").checked;

      console.log("🟢 Clique Confirmar:", { nome, email, duracao, repetir });

      if (!nome || !email) {
        alert("Please fill in name and e-mail.");
        return;
      }

      await reservarHorario(dia, hora, nome, email, duracao, repetir);
      console.log("✅ Reserva criada com sucesso!");
      dlg.close();
    } catch (err) {
      console.error("❌ Erro no botão Confirmar:", err);
      alert("Erro ao confirmar reserva. Veja o console para detalhes.");
    }
  };

  // Botão Cancelar
  newCancel.onclick = () => {
    console.log("❌ Modal fechado sem ação");
    dlg.close();
  };
}

// ===============================
//  CRIAÇÃO DE RESERVAS (PROTEGIDA)
// ===============================
async function reservarHorario(dia, hora, nome, email, duracaoHoras, repetir) {
  try {
    console.log("⚙️ Iniciando reservarHorario()", { dia, hora, nome, email, duracaoHoras, repetir });

    const [hh, mm] = hora.split(":").map(Number);
    const base = new Date(dia);
    base.setHours(hh, mm, 0, 0);

    const agora = new Date();
    if (base < agora) {
      alert("You cannot book a past time.");
      return;
    }

    const idRepeticao = crypto.randomUUID();
    const limite = new Date("2030-12-31");
    const novas = criarReservasParaBloco(base, nome, email, duracaoHoras, idRepeticao);

    if (repetir) {
      let p = new Date(base);
      while (true) {
        p.setDate(p.getDate() + 7);
        if (p > limite) break;
        novas.push(...criarReservasParaBloco(p, nome, email, duracaoHoras, idRepeticao));
      }
    }

    console.log("📤 Enviando reservas:", novas);
    await salvarReservasServidor(novas);
    await gerarCalendario();
  } catch (err) {
    console.error("❌ Erro em reservarHorario():", err);
    alert("Falha ao criar reserva. Veja o console.");
  }
}

function criarReservasParaBloco(inicio, nome, email, duracaoHoras, idRepeticao) {
  const criadas = [];
  const slots = Math.floor((duracaoHoras * 60) / 30);
  for (let i = 0; i < slots; i++) {
    const d = new Date(inicio);
    d.setMinutes(d.getMinutes() + i * 30);
    criadas.push({
      data: localISO(d),
      nome,
      email,
      duracao: duracaoHoras,
      idRepeticao,
    });
  }
  return criadas;
}

// ===============================
//  NAVEGAÇÃO SEMANAL
// ===============================
document.querySelector("#semanaAnterior").onclick = async () => {
  currentDate.setDate(currentDate.getDate() - 7);
  await gerarCalendario();
};
document.querySelector("#semanaProxima").onclick = async () => {
  currentDate.setDate(currentDate.getDate() + 7);
  await gerarCalendario();
};
document.querySelector("#semanaAtualBtn").onclick = async () => {
  currentDate = new Date();
  await gerarCalendario();
};

// ===============================
//  FILTRO MENSAL
// ===============================
document.querySelectorAll("#mesBar button").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const mes = parseInt(btn.getAttribute("data-mes"));
    const anoAtual = currentDate.getFullYear();
    currentDate = new Date(anoAtual, mes, 1);
    await gerarCalendario();
    document.querySelectorAll("#mesBar button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  });
});

// ===============================
//  STARTUP / INICIALIZAÇÃO
// ===============================
window.addEventListener("load", gerarCalendario);
console.log("✅ script.js successfully loaded");

document.addEventListener("DOMContentLoaded", async () => {
  console.log("🚀 Inicializando calendário...");
  await gerarCalendario();
});
