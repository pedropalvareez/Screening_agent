// Candidate chat. The conversation id lives in the URL fragment, which the
// browser never sends to the server or in a Referer. Every message is set with
// textContent: reply text is LLM output the candidate can influence.

const LABELS = {
  es: {
    subtitle: "Asistente virtual (IA)",
    message: "Mensaje",
    placeholder: "Escribe un mensaje",
    send: "Enviar",
    typing: "Leo está escribiendo…",
    otherCity: "Otra ciudad",
    countries: { ES: "España", MX: "México" },
    sendFailed: "No se pudo enviar. Revisa tu conexión e inténtalo de nuevo.",
    loadFailed: "No se pudo cargar la conversación. Recarga la página.",
  },
  en: {
    subtitle: "Virtual assistant (AI)",
    message: "Message",
    placeholder: "Type a message",
    send: "Send",
    typing: "Leo is typing…",
    otherCity: "Other city",
    countries: { ES: "Spain", MX: "Mexico" },
    sendFailed: "Couldn't send. Check your connection and try again.",
    loadFailed: "Couldn't load the conversation. Reload the page.",
  },
};
// Up to the trailing punctuation: "…/privacidad. ¿Empezamos?"
const LINK = /(https:\/\/\S+?)(?=[.,;:!?)]*(?:\s|$))/;

const log = document.getElementById("log");
const options = document.getElementById("options");
const form = document.getElementById("composer");
const field = document.getElementById("message");
const send = document.getElementById("send");

let id = location.hash.slice(1);
let labels = LABELS.es;
let busy = false;

function setLanguage(language) {
  labels = LABELS[language] ?? LABELS.es;
  document.documentElement.lang = language in LABELS ? language : "es";
  document.getElementById("subtitle").textContent = labels.subtitle;
  document.getElementById("message-label").textContent = labels.message;
  field.placeholder = labels.placeholder;
  send.setAttribute("aria-label", labels.send);
}

function add(element) {
  log.append(element);
  element.scrollIntoView({ block: "end" });
}

function bubble(role, text) {
  const p = document.createElement("p");
  p.className = `bubble ${role}`;
  text.split(LINK).forEach((part, i) => {
    if (i % 2 === 0) return p.append(part);
    const a = document.createElement("a");
    a.href = part;
    a.textContent = part;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    p.append(a);
  });
  add(p);
}

function error(text) {
  const p = document.createElement("p");
  p.className = "error";
  p.setAttribute("role", "alert");
  p.textContent = text;
  add(p);
}

function typing() {
  const p = document.createElement("p");
  p.className = "bubble agent typing";
  const label = document.createElement("span");
  label.className = "visually-hidden";
  label.textContent = labels.typing;
  p.append(label, ...[1, 2, 3].map(() => document.createElement("span")));
  add(p);
  return p;
}

function showOptions(cities) {
  options.replaceChildren();
  if (!cities) return;
  for (const [country, names] of Object.entries(cities)) {
    const heading = document.createElement("p");
    heading.className = "country";
    heading.id = `country-${country}`;
    heading.textContent = labels.countries[country] ?? country;
    const group = document.createElement("div");
    group.className = "chips";
    group.setAttribute("role", "group");
    group.setAttribute("aria-labelledby", heading.id);
    for (const name of names) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = name;
      button.addEventListener("click", () => submit(name, false));
      group.append(button);
    }
    options.append(heading, group);
  }
  const other = document.createElement("button");
  other.type = "button";
  other.textContent = labels.otherCity;
  other.addEventListener("click", () => field.focus());
  const chips = document.createElement("div");
  chips.className = "chips";
  chips.append(other);
  options.append(chips);
}

function show(reply) {
  setLanguage(reply.language);
  showOptions(reply.options);
}

function setBusy(value) {
  busy = value;
  send.disabled = value;
  for (const button of options.querySelectorAll("button")) button.disabled = value;
}

const path = () => `/conversations/${encodeURIComponent(id)}`;

// No client timeout: a turn whose provider hangs takes about 2 minutes.
async function request(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function submit(text, typed) {
  text = text.trim();
  if (busy || !text) return;
  setBusy(true);
  bubble("candidate", text);
  if (typed) field.value = "";
  const dots = typing();
  try {
    const reply = await request(`${path()}/messages`, { text });
    dots.remove();
    bubble("agent", reply.text);
    show(reply);
  } catch {
    dots.remove();
    error(labels.sendFailed);
    if (typed && !field.value) field.value = text;
  } finally {
    setBusy(false);
    // The tapped city button is gone: keep focus in the chat, not on <body>.
    if (!typed) field.focus();
  }
}

async function open() {
  setBusy(true);
  try {
    if (id) {
      const response = await fetch(path());
      if (response.ok) {
        const resumed = await response.json();
        for (const line of resumed.transcript) bubble(line.role, line.text);
        return show(resumed.reply);
      }
      if (response.status !== 404) throw new Error(`HTTP ${response.status}`);
    }
    const started = await request("/conversations");
    id = started.id;
    history.replaceState(null, "", `#${id}`);
    bubble("agent", started.reply.text);
    show(started.reply);
  } catch {
    error(labels.loadFailed);
  } finally {
    setBusy(false);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submit(field.value, true);
});
field.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    submit(field.value, true);
  }
});

open();
