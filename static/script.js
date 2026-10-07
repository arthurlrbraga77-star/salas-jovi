// ===============================
//  SALAS JOVI — RESERVA DE SALA (front-end)
// ===============================
"use strict";

// Prefixo onde o app está montado, injetado pelo index.html:
// "" quando roda na raiz ("/"), "/salas/<token>" dentro do JOVI Conecta
const BASE = window.SALAS_BASE || "";

// Sala exibida. Para ter mais salas no futuro, basta acrescentar aqui
// (o "id" é o campo "sala" gravado na API).
const ROOMS = [{ id: "samba", name: "Samba Room" }];
const ROOM = ROOMS[0];

// Grade: slots de 30 min começando de 08:00 até 18:00 (o último termina 18:30)
const FIRST_SLOT = 8 * 60;
const SLOT = 30;
const SLOTS = 21;
const DAY_END = FIRST_SLOT + SLOTS * SLOT;
const REPEAT_UNTIL = "2030-12-31";
const FRESH_MS = 30 * 1000;          // dado mais velho que isso é revalidado ao aparecer
const POLL_MS = 60 * 1000;           // revalida a semana visível com a aba aberta
const PREFETCH_MS = 5 * 60 * 1000;   // vizinhas: só rebusca se o cache for mais velho que isso (a semana é revalidada ao abrir)
const TIMEOUT_MS = 15 * 1000;
const STORE_KEY = "salasJovi.profile";

const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const WD_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MON_LONG = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];

const WIDE = window.matchMedia("(min-width: 900px)");
const FINE_POINTER = window.matchMedia("(pointer: fine)");
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)");

// ===============================
//  ELEMENTOS
// ===============================
const $ = (id) => document.getElementById(id);
const el = {
  roomName: $("roomName"), nowPill: $("nowPill"),
  prev: $("prevWeek"), next: $("nextWeek"), today: $("todayBtn"), weekLabel: $("weekLabel"),
  days: $("days"), hint: $("dayHint"), sched: $("schedule"), toasts: $("toasts"),
  bookDlg: $("bookSheet"), bookForm: $("bookForm"), bookWhen: $("bookWhen"), bookTitle: $("bookTitle"),
  bookError: $("bookError"), nome: $("nome"), nomeErr: $("nomeErr"), email: $("email"), emailErr: $("emailErr"),
  durGroup: $("durGroup"), durHint: $("durHint"), repeat: $("repetir"), repeatHint: $("repeatHint"),
  bookSubmit: $("bookSubmit"),
  infoDlg: $("infoSheet"), infoBadge: $("infoBadge"), infoTitle: $("infoTitle"), infoDate: $("infoDate"),
  infoTime: $("infoTime"), infoEmail: $("infoEmail"), infoError: $("infoError"), infoActions: $("infoActions"),
  cancelOpen: $("cancelOpen"), cancelForm: $("cancelForm"), cancelBack: $("cancelBack"),
  adminPw: $("adminPw"), cancelConfirm: $("cancelConfirm"),
};
const durRadios = Array.from(el.durGroup.querySelectorAll("input[name=dur]"));

// ===============================
//  DATAS E TEXTO
// ===============================
const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const hhmm = (min) => `${pad(Math.floor(min / 60))}:${pad(min % 60)}`;
const slotStart = (s) => FIRST_SLOT + s * SLOT;
const minutesOf = (d) => d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60;
const fmtDay = (d) => `${WD[d.getDay()]}, ${MON[d.getMonth()]} ${d.getDate()}`;
const fmtDayLong = (d) => `${WD_LONG[d.getDay()]}, ${MON_LONG[d.getMonth()]} ${d.getDate()}`;

function parseYmd(texto) {
  const [y, m, d] = texto.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function mondayOf(d) {
  const dia = d.getDay();
  return addDays(d, (dia === 0 ? -6 : 1) - dia);
}

// Semana "de hoje": no fim de semana já mostra a próxima (a atual acabou)
function homeWeek(now = new Date()) {
  const dia = now.getDay();
  return mondayOf(dia === 6 ? addDays(now, 2) : dia === 0 ? addDays(now, 1) : now);
}

// Dia escolhido ao abrir uma semana: hoje (se estiver nela) ou segunda
function defaultDay(monday) {
  const i = Math.round((parseYmd(ymd(new Date())) - monday) / 864e5);
  return i >= 0 && i <= 4 ? i : 0;
}

function fmtWeek(mon) {
  const fri = addDays(mon, 4);
  if (mon.getFullYear() !== fri.getFullYear()) {
    return `${MON[mon.getMonth()]} ${mon.getDate()}, ${mon.getFullYear()} – ${MON[fri.getMonth()]} ${fri.getDate()}, ${fri.getFullYear()}`;
  }
  if (mon.getMonth() !== fri.getMonth()) {
    return `${MON[mon.getMonth()]} ${mon.getDate()} – ${MON[fri.getMonth()]} ${fri.getDate()}, ${fri.getFullYear()}`;
  }
  return `${MON[mon.getMonth()]} ${mon.getDate()} – ${fri.getDate()}, ${fri.getFullYear()}`;
}

function fmtDuration(min) {
  const h = Math.floor(min / 60), m = min % 60;
  return [h ? `${h} h` : "", m ? `${m} min` : ""].filter(Boolean).join(" ");
}

// Todo texto vindo do usuário passa por aqui antes de virar HTML
function esc(texto) {
  return String(texto).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function uid() {
  const c = window.crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  const b = new Uint8Array(16);
  if (c && c.getRandomValues) c.getRandomValues(b);
  else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

const icon = (name) => `<svg class="ic" aria-hidden="true"><use href="#i-${name}"/></svg>`;

// ===============================
//  ESTADO E CACHE
// ===============================
const state = {
  monday: homeWeek(),
  day: 0,
  model: null,       // semana desenhada agora (ver buildModel)
  paintedSig: "",
  errorKey: null,    // semana cuja carga falhou (mostra o estado de erro)
  todayKey: ymd(new Date()),
};
state.day = defaultDay(state.monday);

const cache = new Map();     // "sala|segunda" -> { items, at, sig }
const inflight = new Map();  // "sala|segunda#epoch" -> Promise
let epoch = 0;               // muda a cada reserva/cancelamento: respostas antigas são descartadas
let viewSeq = 0;             // muda a cada troca de semana: respostas atrasadas não redesenham
let syncing = null;          // revalidação disparada depois de uma alteração
let sheetBusy = false;

const weekKey = (mon) => `${ROOM.id}|${ymd(mon)}`;

function setCache(key, items, at) {
  cache.delete(key);
  cache.set(key, { items, at, sig: JSON.stringify(items) });
  if (cache.size > 24) {
    const keep = new Set([weekKey(state.monday), weekKey(homeWeek())]);
    for (const k of cache.keys()) {
      if (!keep.has(k)) { cache.delete(k); break; }
    }
  }
}

// ===============================
//  API
// ===============================
async function errorText(res) {
  try {
    const corpo = await res.clone().json();
    if (corpo && typeof corpo.error === "string" && corpo.error) return corpo.error;
  } catch (e) {
    // resposta não é JSON
  }
  const padrao = {
    403: "Incorrect password", 404: "Reservation not found", 413: "Request too large",
    503: "The server is busy, please try again",
  };
  return padrao[res.status] || `Unexpected error (HTTP ${res.status})`;
}

// Busca a semana (segunda a sexta, inclusive) da sala. Uma só requisição por
// semana em andamento; o resultado só entra no cache se nada mudou desde o início.
function fetchWeek(mon) {
  const key = weekKey(mon);
  const startedAt = epoch;
  const voo = `${key}#${startedAt}`;
  if (inflight.has(voo)) return inflight.get(voo);

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  const params = new URLSearchParams({ inicio: ymd(mon), fim: ymd(addDays(mon, 4)), sala: ROOM.id });

  const p = fetch(BASE + "/api/reservas?" + params.toString(), {
    signal: ctrl.signal, cache: "no-store", headers: { Accept: "application/json" },
  })
    .then(async (res) => {
      if (!res.ok) throw new Error(await errorText(res));
      let corpo;
      try {
        corpo = await res.json();
      } catch (e) {
        throw new Error("Unexpected answer from the server.");
      }
      const lista = corpo && Array.isArray(corpo.reservas) ? corpo.reservas : [];
      const items = lista.filter((r) => r && typeof r.data === "string" && r.sala === ROOM.id);
      if (startedAt === epoch) setCache(key, items, Date.now());
      return items;
    })
    .catch((err) => {
      if (err && err.name === "AbortError") throw new Error("The server took too long to answer.");
      if (err instanceof TypeError) throw new Error("Couldn't reach the server. Check your connection.");
      throw err;
    })
    .finally(() => {
      clearTimeout(timer);
      inflight.delete(voo);
    });
  inflight.set(voo, p);
  return p;
}

async function revalidate() {
  const seq = viewSeq;
  const key = weekKey(state.monday);
  try {
    await fetchWeek(state.monday);
    if (seq !== viewSeq) return;
    paint();
    prefetchAround();
  } catch (err) {
    if (seq !== viewSeq) return;
    if (!cache.has(key)) renderError(err.message);
  }
}

// Semanas vizinhas, quando o navegador estiver ocioso
function prefetchAround() {
  const run = () => {
    for (const delta of [7, -7]) {
      const mon = addDays(state.monday, delta);
      const e = cache.get(weekKey(mon));
      if (!e || Date.now() - e.at > PREFETCH_MS) fetchWeek(mon).catch(() => {});
    }
  };
  if ("requestIdleCallback" in window) window.requestIdleCallback(run, { timeout: 2000 });
  else setTimeout(run, 300);
}

// Aplica uma reserva/cancelamento já confirmado pelo servidor a todas as semanas
// em cache (a tela muda na hora) e marca tudo para revalidar.
function applyLocalChange({ add, removeId }) {
  epoch++;
  for (const [key, entry] of Array.from(cache)) {
    let items = entry.items;
    if (removeId) items = items.filter((r) => r.idRepeticao !== removeId && r.data !== removeId);
    if (add) {
      const ini = key.split("|")[1];
      const fim = ymd(addDays(parseYmd(ini), 4));
      items = items.concat(add.filter((r) => {
        const dia = r.data.slice(0, 10);
        return dia >= ini && dia <= fim;
      }).map((r) => Object.assign({ local: true }, r)));
    }
    setCache(key, items, 0);
  }
  paint();
  syncing = revalidate();
}

// ===============================
//  MODELO DA SEMANA
// ===============================
// Junta os slots seguidos da mesma reserva (mesmo idRepeticao + nome) num bloco só.
function buildModel(items, mon, now) {
  const today = ymd(now);
  const nowMin = minutesOf(now);
  const days = [];
  const porDia = new Map();
  for (let i = 0; i < 5; i++) {
    const date = addDays(mon, i);
    const key = ymd(date);
    const d = {
      i, date, key, isToday: key === today, isPast: key < today,
      runs: [], occ: new Array(SLOTS).fill(null),
    };
    days.push(d);
    porDia.set(key, []);
  }

  for (const r of items) {
    const lista = porDia.get(r.data.slice(0, 10));
    const h = Number(r.data.slice(11, 13)), m = Number(r.data.slice(14, 16));
    if (!lista || !Number.isFinite(h) || !Number.isFinite(m)) continue;
    const ini = h * 60 + m;
    lista.push({ start: ini - (ini % SLOT), r });
  }

  for (const d of days) {
    const lista = porDia.get(d.key).sort((a, b) => a.start - b.start);
    let run = null;
    for (const it of lista) {
      if (run && it.start === run.end && it.r.idRepeticao === run.r.idRepeticao && it.r.nome === run.r.nome) {
        run.end += SLOT;
      } else if (!run || it.start >= run.end) {
        run = { day: d.i, start: it.start, end: it.start + SLOT, r: it.r };
        d.runs.push(run);
      }
    }
    for (const run of d.runs) {
      run.past = d.isPast || (d.isToday && run.end <= nowMin);
      run.live = d.isToday && run.start <= nowMin && nowMin < run.end;
      const a = Math.max(0, (run.start - FIRST_SLOT) / SLOT);
      const b = Math.min(SLOTS, (run.end - FIRST_SLOT) / SLOT);
      run.row = a;
      run.span = b - a;
      for (let s = a; s < b; s++) d.occ[s] = run;
    }
    d.visible = d.runs.filter((run) => run.span > 0);
  }
  return { mon, key: weekKey(mon), days, nowMin };
}

function slotPast(d, s, nowMin) {
  return d.isPast || (d.isToday && slotStart(s) + SLOT <= nowMin);
}

// Faixa de 30 min em que o relógio está (-1 antes das 08:00, SLOTS depois das 18:30)
function slotPhase(nowMin) {
  return Math.min(SLOTS, Math.max(-1, Math.floor((nowMin - FIRST_SLOT) / SLOT)));
}

// Slot da hora atual (hoje), ou -1
function nowSlot(nowMin) {
  if (nowMin < FIRST_SLOT || nowMin >= DAY_END) return -1;
  return Math.floor((nowMin - FIRST_SLOT) / SLOT);
}

// ===============================
//  DESENHO
// ===============================
function headHtml(days) {
  let h = '<div class="sched-head" aria-hidden="true"><div></div>';
  for (const d of days) {
    h += `<div class="dh${d.isToday ? " is-today" : ""}${d.isPast ? " is-past" : ""}">` +
      `<span class="dh-wd">${WD[d.date.getDay()]}</span><span class="dh-d">${d.date.getDate()}</span></div>`;
  }
  return h + "</div>";
}

function timesHtml(cur) {
  let h = '<div class="times" aria-hidden="true">';
  for (let s = 0; s < SLOTS; s++) {
    h += `<div class="t${s === cur ? " is-now" : ""}"><span>${hhmm(slotStart(s))}</span></div>`;
  }
  return h + "</div>";
}

function colOpen(d) {
  return `<div class="day-col${d.isToday ? " is-today" : ""}${d.i === state.day ? " is-sel" : ""}" ` +
    `data-day="${d.i}" role="group" aria-label="${fmtDayLong(d.date)}">`;
}

function freeHtml(d, s, nowMin) {
  const pos = `grid-row:${s + 1}`;
  if (slotPast(d, s, nowMin)) return `<div class="slot past" style="${pos}"></div>`;
  const agora = d.isToday && s === nowSlot(nowMin);
  return `<button type="button" class="slot free${agora ? " is-now" : ""}" style="${pos}" ` +
    `data-act="book" data-day="${d.i}" data-slot="${s}" data-key="f${d.i}-${s}" aria-haspopup="dialog" ` +
    `aria-label="Book ${fmtDayLong(d.date)} at ${hhmm(slotStart(s))}${agora ? " (now)" : ""}">` +
    `${icon("plus")}<span class="slot-label">Book</span>${agora ? '<span class="slot-now">Now</span>' : ""}</button>`;
}

function blockHtml(d, run) {
  const faixa = `${hhmm(run.start)} – ${hhmm(run.end)}`;
  const titulo = esc(run.r.nome);
  const quem = esc(run.r.email);
  const cls = `blk${run.past ? " past" : ""}${run.live ? " is-live" : ""}`;
  const style = `grid-row:${run.row + 1} / span ${run.span};--lines:${Math.min(3, run.span)}`;
  const dentro = `<span class="blk-title">${titulo}</span>` +
    `<span class="blk-time">${faixa}${run.live ? '<span class="blk-now">Now</span>' : ""}</span>` +
    (run.span >= 3 ? `<span class="blk-by">${quem}</span>` : "");
  if (run.past) return `<div class="${cls}" style="${style}">${dentro}</div>`;
  return `<button type="button" class="${cls}" style="${style}" data-act="info" data-day="${d.i}" ` +
    `data-slot="${run.row}" data-key="b${d.i}-${run.row}" aria-haspopup="dialog" ` +
    `aria-label="${titulo}, ${faixa}, booked by ${quem}">${dentro}</button>`;
}

// Redesenha a semana numa passada só (uma string, um innerHTML), mantendo o foco
function renderSchedule(m) {
  const ativo = document.activeElement;
  const focoKey = ativo && el.sched.contains(ativo) && ativo.dataset ? ativo.dataset.key : null;

  const cur = m.days.some((d) => d.isToday) ? nowSlot(m.nowMin) : -1;
  let cols = "";
  for (const d of m.days) {
    cols += colOpen(d);
    for (let s = 0; s < SLOTS;) {
      const run = d.occ[s];
      if (run) {
        cols += blockHtml(d, run);
        s = run.row + run.span;
      } else {
        cols += freeHtml(d, s, m.nowMin);
        s++;
      }
    }
    if (d.isToday && cur >= 0) {
      const f = (m.nowMin - slotStart(cur)) / SLOT;
      cols += `<div class="now-line" style="--i:${cur};--f:${f.toFixed(3)}" aria-hidden="true"></div>`;
    }
    cols += "</div>";
  }
  el.sched.innerHTML = headHtml(m.days) + '<div class="sched-body">' + timesHtml(cur) + cols + "</div>";
  el.sched.setAttribute("aria-busy", "false");

  if (focoKey) {
    const outra = focoKey[0] === "f" ? "b" + focoKey.slice(1) : "f" + focoKey.slice(1);
    const alvo = el.sched.querySelector(`[data-key="${focoKey}"]`) || el.sched.querySelector(`[data-key="${outra}"]`);
    if (alvo) alvo.focus({ preventScroll: true });
  }
}

function renderSkeleton() {
  state.paintedSig = "";
  state.model = null;
  const today = ymd(new Date());
  const days = [];
  for (let i = 0; i < 5; i++) {
    const date = addDays(state.monday, i);
    days.push({ i, date, isToday: ymd(date) === today, isPast: ymd(date) < today });
  }
  let cols = "";
  for (const d of days) {
    cols += colOpen(d);
    for (let s = 0; s < SLOTS; s++) cols += `<div class="slot skel" style="grid-row:${s + 1}"></div>`;
    cols += "</div>";
  }
  el.sched.innerHTML = headHtml(days) + '<div class="sched-body">' + timesHtml(-1) + cols + "</div>";
  el.sched.setAttribute("aria-busy", "true");
  el.hint.hidden = true;
}

function renderError(msg) {
  const key = weekKey(state.monday);
  const atual = el.sched.querySelector(".state-msg");
  if (state.errorKey === key && atual) {
    atual.textContent = msg;
    return;
  }
  state.errorKey = key;
  state.paintedSig = "";
  state.model = null;
  el.sched.innerHTML = `<div class="state" role="alert"><div class="state-ic">${icon("alert")}</div>` +
    `<p class="state-title">Couldn't load the schedule</p><p class="state-msg">${esc(msg)}</p>` +
    `<button type="button" class="jovi-btn jovi-btn-primary" data-act="retry">Retry</button></div>`;
  el.sched.setAttribute("aria-busy", "false");
  el.hint.hidden = true;
}

// Desenha a semana visível a partir do cache (esqueleto se ainda não tem dados).
// Só refaz o HTML quando os dados ou o minuto mudam.
function paint() {
  const key = weekKey(state.monday);
  const entry = cache.get(key);
  if (!entry) {
    if (state.errorKey !== key && (state.model || !el.sched.querySelector(".skel"))) renderSkeleton();
    updateNowPill();
    return;
  }
  state.errorKey = null;
  const now = new Date();
  const nowMin = minutesOf(now);
  // O HTML só depende do dia e da faixa de 30 min (passado / agora / livre);
  // dentro da mesma faixa basta mover a linha de "agora".
  const sig = `${key}\n${ymd(now)}\n${slotPhase(nowMin)}\n${entry.sig}`;
  if (sig !== state.paintedSig) {
    state.paintedSig = sig;
    state.model = buildModel(entry.items, state.monday, now);
    renderSchedule(state.model);
    if (el.bookDlg.open && book) refreshDurations();
  } else if (state.model) {
    state.model.nowMin = nowMin;
    moveNowLine(nowMin);
  }
  updateSelToday();
  updateHint();
  updateNowPill();
}

function renderChips() {
  const today = ymd(new Date());
  let h = "";
  for (let i = 0; i < 5; i++) {
    const d = addDays(state.monday, i);
    const k = ymd(d);
    const hoje = k === today;
    h += `<button type="button" class="chip${hoje ? " is-today" : ""}${k < today ? " is-past" : ""}" ` +
      `data-day="${i}" aria-pressed="${i === state.day}"${hoje ? ' aria-current="date"' : ""} ` +
      `aria-label="${fmtDayLong(d)}${hoje ? " (today)" : ""}">` +
      `<span class="chip-wd">${WD[d.getDay()]}</span><span class="chip-d">${d.getDate()}</span></button>`;
  }
  el.days.innerHTML = h;
}

function selectDay(i) {
  state.day = i;
  for (const b of el.days.children) b.setAttribute("aria-pressed", String(Number(b.dataset.day) === i));
  for (const c of el.sched.querySelectorAll(".day-col")) c.classList.toggle("is-sel", Number(c.dataset.day) === i);
  updateSelToday();
  updateHint();
}

// No celular a coluna de horários só marca "agora" quando o dia escolhido é hoje
function updateSelToday() {
  el.sched.classList.toggle("sel-today", ymd(addDays(state.monday, state.day)) === ymd(new Date()));
}

// Move a linha de "agora" sem redesenhar a grade
function moveNowLine(nowMin) {
  const linha = el.sched.querySelector(".now-line");
  const cur = nowSlot(nowMin);
  if (!linha || cur < 0) return;
  linha.style.setProperty("--f", ((nowMin - slotStart(cur)) / SLOT).toFixed(3));
}

function setHint(texto) {
  if (!texto) {
    el.hint.hidden = true;
    return;
  }
  el.hint.innerHTML = icon("cal") + "<span></span>";
  el.hint.lastChild.textContent = texto;
  el.hint.hidden = false;
}

function updateHint() {
  const m = state.model;
  if (!m || m.key !== weekKey(state.monday)) return setHint("");
  if (WIDE.matches) {
    const vazia = m.days.every((d) => d.visible.length === 0);
    const passou = m.days.every((d) => d.isPast || (d.isToday && m.nowMin >= DAY_END));
    return setHint(vazia && !passou ? "No bookings this week yet — every slot is free." : "");
  }
  const d = m.days[state.day];
  if (d.isPast) return setHint("This day has already passed.");
  if (d.isToday && m.nowMin >= DAY_END) return setHint("Today's schedule is over — pick another day.");
  setHint(d.visible.length === 0 ? "Nothing booked yet — the room is free all day." : "");
}

// "Free now / In use" no topo (só em dia útil, dentro do horário)
let nowAction = null;
function updateNowPill() {
  const now = new Date();
  const mon = mondayOf(now);
  const entry = cache.get(weekKey(mon));
  const s = nowSlot(minutesOf(now));
  const fimDeSemana = now.getDay() === 0 || now.getDay() === 6;
  if (fimDeSemana || !entry || s < 0) {
    el.nowPill.hidden = true;
    nowAction = null;
    return;
  }
  const m = state.model && state.model.key === weekKey(mon) ? state.model : buildModel(entry.items, mon, now);
  const d = m.days.find((x) => x.isToday);
  const run = d.occ[s];
  let texto, cta;
  if (run) {
    texto = `In use until ${hhmm(run.end)}`;
    cta = "Details";
    nowAction = { act: "info", day: d.i, slot: run.row };
  } else {
    let k = s + 1;
    while (k < SLOTS && !d.occ[k]) k++;
    texto = k < SLOTS ? `Free now until ${hhmm(slotStart(k))}` : "Free for the rest of the day";
    cta = "Book now";
    nowAction = { act: "book", day: d.i, slot: s };
  }
  el.nowPill.classList.toggle("is-busy", Boolean(run));
  el.nowPill.innerHTML = '<span class="now-dot" aria-hidden="true"></span><span></span><span class="now-cta"></span>';
  el.nowPill.children[1].textContent = texto;
  el.nowPill.children[2].textContent = cta;
  el.nowPill.hidden = false;
}

// ===============================
//  NAVEGAÇÃO
// ===============================
function showWeek(mon, day) {
  viewSeq++;
  state.errorKey = null;
  state.monday = mon;
  state.day = day === undefined ? defaultDay(mon) : day;
  el.weekLabel.textContent = fmtWeek(mon);
  el.today.classList.toggle("is-here", ymd(mon) === ymd(homeWeek()));
  renderChips();
  paint();
  selectDay(state.day);
  const entry = cache.get(weekKey(mon));
  if (!entry || Date.now() - entry.at > FRESH_MS) revalidate();
  else prefetchAround();
}

function goToday() {
  const mon = homeWeek();
  showWeek(mon, defaultDay(mon));
}

el.prev.addEventListener("click", () => showWeek(addDays(state.monday, -7)));
el.next.addEventListener("click", () => showWeek(addDays(state.monday, 7)));
el.today.addEventListener("click", () => {
  goToday();
  const linha = el.sched.querySelector(".day-col.is-sel .now-line");
  if (linha) linha.scrollIntoView({ block: "center", behavior: REDUCED_MOTION.matches ? "auto" : "smooth" });
});

el.days.addEventListener("click", (e) => {
  const b = e.target.closest(".chip");
  if (b) selectDay(Number(b.dataset.day));
});
el.days.addEventListener("keydown", (e) => {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  const i = Math.min(4, Math.max(0, state.day + (e.key === "ArrowRight" ? 1 : -1)));
  selectDay(i);
  el.days.children[i].focus();
  e.preventDefault();
});

// Um único listener para toda a grade
el.sched.addEventListener("click", (e) => {
  const alvo = e.target.closest("[data-act]");
  if (!alvo || !el.sched.contains(alvo)) return;
  const act = alvo.dataset.act;
  if (act === "retry") {
    state.errorKey = null;
    renderSkeleton();
    revalidate();
  } else if (act === "book") {
    openBook(Number(alvo.dataset.day), Number(alvo.dataset.slot), alvo);
  } else if (act === "info") {
    openInfo(Number(alvo.dataset.day), Number(alvo.dataset.slot), alvo);
  }
});

el.nowPill.addEventListener("click", () => {
  if (!nowAction) return;
  const a = nowAction;
  const mon = mondayOf(new Date());
  if (ymd(state.monday) !== ymd(mon)) showWeek(mon, a.day);
  else selectDay(a.day);
  if (a.act === "book") openBook(a.day, a.slot, el.nowPill);
  else openInfo(a.day, a.slot, el.nowPill);
});

WIDE.addEventListener("change", updateHint);

// ===============================
//  FOLHAS (dialog)
// ===============================
let voltarFoco = { key: null, el: null };

function openSheet(dlg, trigger, foco) {
  voltarFoco = { key: (trigger && trigger.dataset && trigger.dataset.key) || null, el: trigger || null };
  if (!dlg.open) dlg.showModal();
  document.documentElement.classList.add("has-modal");
  foco.focus({ preventScroll: true });
}

function closeSheet(dlg) {
  if (dlg.open && !sheetBusy) dlg.close();
}

function restoreFocus() {
  const { key, el: antes } = voltarFoco;
  let alvo = null;
  if (key) {
    const outra = (key[0] === "f" ? "b" : "f") + key.slice(1);
    alvo = el.sched.querySelector(`[data-key="${key}"]`) || el.sched.querySelector(`[data-key="${outra}"]`);
  }
  if (!alvo && antes && antes.isConnected && !antes.hidden) alvo = antes;
  if (!alvo) alvo = el.days.querySelector('[aria-pressed="true"]') || el.today;
  alvo.focus({ preventScroll: true });
}

for (const dlg of [el.bookDlg, el.infoDlg]) {
  dlg.addEventListener("click", (e) => {
    // clique no fundo escuro (fora da folha) ou num botão "fechar"
    if (e.target === dlg || e.target.closest("[data-close]")) closeSheet(dlg);
  });
  dlg.addEventListener("cancel", (e) => {
    if (sheetBusy) e.preventDefault();
  });
  dlg.addEventListener("close", () => {
    document.documentElement.classList.remove("has-modal");
    restoreFocus();
  });
}

function setBusy(btn, busy, texto) {
  sheetBusy = busy;
  if (busy) {
    btn.dataset.label = btn.textContent;
    btn.textContent = texto;
  } else if (btn.dataset.label) {
    btn.textContent = btn.dataset.label;
  }
  btn.disabled = busy;
  btn.setAttribute("aria-busy", String(busy));
}

function showAlert(box, msg) {
  box.textContent = msg;
  box.hidden = !msg;
}

// ===============================
//  NOVA RESERVA
// ===============================
let book = null;   // { mon, dayIdx, date, slot, start }

function loadProfile() {
  try {
    const v = JSON.parse(window.localStorage.getItem(STORE_KEY) || "null");
    if (v && typeof v === "object") {
      return {
        nome: typeof v.nome === "string" ? v.nome.slice(0, 200) : "",
        email: typeof v.email === "string" ? v.email.slice(0, 200) : "",
      };
    }
  } catch (e) {
    // armazenamento bloqueado (modo privado etc.)
  }
  return { nome: "", email: "" };
}

function saveProfile(nome, email) {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify({ nome, email }));
  } catch (e) {
    // sem armazenamento: só não lembra
  }
}

function fieldError(input, box, msg) {
  box.textContent = msg;
  box.hidden = !msg;
  if (msg) input.setAttribute("aria-invalid", "true");
  else input.removeAttribute("aria-invalid");
  return !msg;
}

function weeksUntilLimit(date) {
  let n = 0;
  for (let d = date; ymd(d) <= REPEAT_UNTIL; d = addDays(d, 7)) n++;
  return Math.max(1, n);
}

function openBook(dayIdx, slot, trigger) {
  const m = state.model;
  if (!m) return;
  const d = m.days[dayIdx];
  if (d.occ[slot] || slotPast(d, slot, minutesOf(new Date()))) {
    toast("That time is no longer available.", "danger");
    state.paintedSig = "";
    paint();
    return;
  }
  book = { mon: m.mon, key: m.key, dayIdx, date: d.date, slot, start: slotStart(slot) };

  el.bookWhen.textContent = `${fmtDay(d.date)} · ${hhmm(book.start)}`;
  showAlert(el.bookError, "");
  fieldError(el.nome, el.nomeErr, "");
  fieldError(el.email, el.emailErr, "");
  const perfil = loadProfile();
  el.nome.value = perfil.nome;
  el.email.value = perfil.email;
  el.repeat.checked = false;
  for (const r of durRadios) r.checked = false;
  setBusy(el.bookSubmit, false);
  refreshDurations(1);
  updateRepeatHint();

  // No celular não abre o teclado sozinho (a folha ficaria escondida)
  let foco = el.bookTitle;
  if (FINE_POINTER.matches) foco = !el.nome.value ? el.nome : !el.email.value ? el.email : el.bookSubmit;
  openSheet(el.bookDlg, trigger, foco);
}

// Habilita só as durações que cabem: sem passar por cima de outra reserva e até 18:30
function refreshDurations(preferida) {
  const m = state.model;
  if (!book || !m || m.key !== book.key) return;
  const d = m.days[book.dayIdx];
  let livres = 0;
  while (book.slot + livres < SLOTS && !d.occ[book.slot + livres]) livres++;

  const marcada = durRadios.find((r) => r.checked);
  const quer = marcada ? Number(marcada.value) : preferida || 1;
  let escolhida = null;
  for (const r of durRadios) {
    const n = Number(r.value) * 2;
    const cabe = n <= livres;
    r.disabled = !cabe;
    r.parentElement.title = cabe ? "" :
      book.slot + n > SLOTS && book.slot + livres >= SLOTS ? "Would end after 18:30" : "Overlaps another booking";
    if (cabe && Number(r.value) <= quer) escolhida = r;
  }
  for (const r of durRadios) r.checked = r === escolhida;
  el.bookSubmit.disabled = !escolhida;
  if (!escolhida && el.bookError.hidden) {
    showAlert(el.bookError, "This time has just been booked by someone else. Pick another slot.");
  }
  updateDurHint(livres);
}

function updateDurHint(livres) {
  const marcada = durRadios.find((r) => r.checked);
  if (!book || !marcada) {
    el.durHint.textContent = "";
    return;
  }
  const fim = book.start + Number(marcada.value) * 60;
  let texto = `${hhmm(book.start)} – ${hhmm(fim)}`;
  if (livres !== undefined && book.slot + livres < SLOTS) texto += ` · next booking at ${hhmm(slotStart(book.slot + livres))}`;
  else if (durRadios.some((r) => r.disabled)) texto += " · bookings end at 18:30";
  el.durHint.textContent = texto;
}

function updateRepeatHint() {
  if (!book) return;
  const quando = `${WD_LONG[book.date.getDay()]} at ${hhmm(book.start)}`;
  el.repeatHint.textContent = el.repeat.checked
    ? `Every ${quando} · ${weeksUntilLimit(book.date)} dates until Dec 31, 2030`
    : `Same time every week, until Dec 31, 2030`;
}

el.durGroup.addEventListener("change", () => {
  const m = state.model;
  if (!book || !m) return;
  const d = m.days[book.dayIdx];
  let livres = 0;
  while (book.slot + livres < SLOTS && !d.occ[book.slot + livres]) livres++;
  updateDurHint(livres);
});
el.repeat.addEventListener("change", updateRepeatHint);
el.nome.addEventListener("input", () => fieldError(el.nome, el.nomeErr, ""));
el.email.addEventListener("input", () => fieldError(el.email, el.emailErr, ""));

// Mesmo formato de sempre: um item por slot de 30 min, todos com o mesmo idRepeticao
function buildItems(date, start, horas, repetir, nome, email) {
  const id = uid();
  const n = Math.round(horas * 2);
  const itens = [];
  let d = date;
  do {
    const dia = ymd(d);
    for (let i = 0; i < n; i++) {
      itens.push({ data: `${dia}T${hhmm(start + i * SLOT)}`, nome, email, duracao: horas, idRepeticao: id, sala: ROOM.id });
    }
    d = addDays(d, 7);
  } while (repetir && ymd(d) <= REPEAT_UNTIL);
  return itens;
}

el.bookForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (sheetBusy || !book) return;
  const nome = el.nome.value.trim();
  const email = el.email.value.trim();
  const nomeOk = fieldError(el.nome, el.nomeErr, nome ? "" : "Please enter a title.");
  const emailOk = fieldError(el.email, el.emailErr,
    !email ? "Please enter your e-mail." : /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? "" : "Please enter a valid e-mail.");
  if (!nomeOk || !emailOk) {
    (nomeOk ? el.email : el.nome).focus();
    return;
  }
  const marcada = durRadios.find((r) => r.checked && !r.disabled);
  if (!marcada) return;

  const horas = Number(marcada.value);
  const repetir = el.repeat.checked;
  saveProfile(nome, email);
  const itens = buildItems(book.date, book.start, horas, repetir, nome, email);
  const resumo = `${fmtDay(book.date)} · ${hhmm(book.start)} – ${hhmm(book.start + horas * 60)}`;

  showAlert(el.bookError, "");
  setBusy(el.bookSubmit, true, "Booking…");
  let res;
  try {
    res = await fetch(BASE + "/api/reservas", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(itens),
    });
  } catch (err) {
    setBusy(el.bookSubmit, false);
    showAlert(el.bookError, "Couldn't reach the server. Check your connection and try again.");
    return;
  }

  if (res.status === 201) {
    const aviso = repetir ? `Booked weekly from ${resumo} (${weeksUntilLimit(book.date)} dates)` : `Booked ${resumo}`;
    setBusy(el.bookSubmit, false);
    book = null;
    applyLocalChange({ add: itens });
    el.bookDlg.close();
    toast(aviso);
    return;
  }

  const msg = await errorText(res);
  setBusy(el.bookSubmit, false);
  showAlert(el.bookError, res.status === 409 ? `${msg}. Choose another time or duration.` : msg);
  if (res.status === 409) revalidate();
});

// ===============================
//  DETALHES E CANCELAMENTO
// ===============================
let info = null;   // { run }

async function openInfo(dayIdx, slot, trigger) {
  let run = state.model && state.model.days[dayIdx].occ[slot];
  if (run && run.r.local && syncing) {
    // acabou de ser criada: espera o id definitivo do servidor
    await syncing.catch(() => {});
    run = state.model && state.model.days[dayIdx].occ[slot];
  }
  if (!run) return;
  info = { run };
  const d = state.model.days[dayIdx];
  el.infoTitle.textContent = run.r.nome;
  el.infoDate.textContent = fmtDayLong(d.date);
  el.infoTime.textContent = `${hhmm(run.start)} – ${hhmm(run.end)} · ${fmtDuration(run.end - run.start)}`;
  el.infoEmail.textContent = run.r.email;
  el.infoBadge.textContent = run.live ? "In progress" : "Booked";
  el.infoBadge.className = `jovi-badge ${run.live ? "jovi-badge-warning" : "jovi-badge-info"}`;
  showAlert(el.infoError, "");
  el.infoActions.hidden = false;
  el.cancelForm.hidden = true;
  el.adminPw.value = "";
  el.cancelOpen.disabled = Boolean(run.r.local);
  setBusy(el.cancelConfirm, false);
  openSheet(el.infoDlg, trigger, el.infoTitle);
}

el.cancelOpen.addEventListener("click", () => {
  el.infoActions.hidden = true;
  el.cancelForm.hidden = false;
  showAlert(el.infoError, "");
  el.adminPw.focus();
});

el.cancelBack.addEventListener("click", () => {
  el.cancelForm.hidden = true;
  el.infoActions.hidden = false;
  showAlert(el.infoError, "");
  el.cancelOpen.focus();
});

el.adminPw.addEventListener("input", () => showAlert(el.infoError, ""));

el.cancelForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (sheetBusy || !info) return;
  const senha = el.adminPw.value;
  if (!senha) {
    showAlert(el.infoError, "Enter the admin password.");
    el.adminPw.focus();
    return;
  }
  const r = info.run.r;
  const id = r.idRepeticao || r.data;

  setBusy(el.cancelConfirm, true, "Cancelling…");
  let res;
  try {
    res = await fetch(BASE + "/api/reservas/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ id, senha, sala: r.sala }),
    });
  } catch (err) {
    setBusy(el.cancelConfirm, false);
    showAlert(el.infoError, "Couldn't reach the server. Check your connection and try again.");
    return;
  }

  setBusy(el.cancelConfirm, false);
  if (res.ok) {
    info = null;
    el.adminPw.value = "";
    applyLocalChange({ removeId: id });
    el.infoDlg.close();
    toast("Reservation cancelled");
    return;
  }
  showAlert(el.infoError, await errorText(res));
  if (res.status === 403) {
    el.adminPw.select();
    el.adminPw.focus();
  } else if (res.status === 404) {
    revalidate();
  }
});

// ===============================
//  AVISOS (TOASTS)
// ===============================
function toast(texto, tipo = "success") {
  const t = document.createElement("div");
  t.className = `toast toast-${tipo}`;
  if (tipo === "danger") t.setAttribute("role", "alert");
  t.innerHTML = `<span class="toast-ic">${icon(tipo === "danger" ? "alert" : "check")}</span><span></span>`;
  t.lastChild.textContent = texto;
  el.toasts.appendChild(t);
  while (el.toasts.children.length > 3) el.toasts.firstElementChild.remove();
  setTimeout(() => {
    t.classList.add("is-out");
    setTimeout(() => t.remove(), 250);
  }, tipo === "danger" ? 5000 : 3500);
}

// ===============================
//  RELÓGIO: marca de "agora", virada do dia e revalidação
// ===============================
function tick() {
  if (document.hidden) return;
  const hoje = ymd(new Date());
  if (hoje !== state.todayKey) {
    state.todayKey = hoje;
    state.paintedSig = "";
    el.today.classList.toggle("is-here", ymd(state.monday) === ymd(homeWeek()));
    renderChips();
  }
  paint();
  const e = cache.get(weekKey(state.monday));
  if (!e || Date.now() - e.at > POLL_MS) revalidate();
}

setInterval(tick, 15 * 1000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) tick();
});

// ===============================
//  INÍCIO
// ===============================
el.roomName.textContent = ROOM.name;
showWeek(state.monday, state.day);
