// Candidate chat. The conversation id lives in the URL fragment, which the
// browser never sends to the server or in a Referer. Every message is set with
// textContent: reply text is LLM output the candidate can influence.

const LABELS = {
  es: {
    subtitle: "Asistente virtual",
    message: "Mensaje",
    placeholder: "Escribe un mensaje",
    send: "Enviar",
    typing: "Leo está escribiendo…",
    otherCity: "Otra ciudad",
    countries: { ES: "España", MX: "México" },
    sendFailed: "No se pudo enviar. Revisa tu conexión e inténtalo de nuevo.",
    loadFailed: "No se pudo cargar la conversación. Recarga la página.",
    talk: "Hablar con Leo",
    listening: "Te escucho…",
    thinking: "Leo está pensando…",
    speaking: "Leo está hablando · puedes interrumpir",
    micFailed: "No se pudo usar el micrófono. Puedes seguir escribiendo.",
    voiceFailed: "La voz dejó de funcionar. Puedes seguir escribiendo.",
    // Played the moment the candidate stops talking: neutral, they never rate
    // the answer (#25), and they are not in the transcript.
    acks: [
      "acks/es-vale.mp3",
      "acks/es-mm-vale.mp3",
      "acks/es-a-ver.mp3",
      "acks/es-aja.mp3",
    ],
  },
  en: {
    subtitle: "Virtual assistant",
    message: "Message",
    placeholder: "Type a message",
    send: "Send",
    typing: "Leo is typing…",
    otherCity: "Other city",
    countries: { ES: "Spain", MX: "Mexico" },
    sendFailed: "Couldn't send. Check your connection and try again.",
    loadFailed: "Couldn't load the conversation. Reload the page.",
    talk: "Talk to Leo",
    listening: "Listening…",
    thinking: "Leo is thinking…",
    speaking: "Leo is speaking · you can interrupt",
    micFailed: "Couldn't use the microphone. You can keep typing.",
    voiceFailed: "Voice stopped working. You can keep typing.",
    acks: [
      "acks/en-okay.mp3",
      "acks/en-alright.mp3",
      "acks/en-lets-see.mp3",
      "acks/en-mm-hm.mp3",
    ],
  },
};
// Up to the trailing punctuation: "…/privacidad. ¿Empezamos?"
const LINK = /(https:\/\/\S+?)(?=[.,;:!?)]*(?:\s|$))/;

const log = document.getElementById("log");
const options = document.getElementById("options");
const form = document.getElementById("composer");
const field = document.getElementById("message");
const send = document.getElementById("send");
const talk = document.getElementById("talk");
const voiceStatus = document.getElementById("voice-status");

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
  talk.setAttribute("aria-label", labels.talk);
  talk.title = labels.talk;
}

function scrollDown() {
  log.scrollTop = log.scrollHeight;
}

function add(element) {
  log.append(element);
  scrollDown();
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
  scrollDown(); // the options take room from the log
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
  if (voice) hush();
  bubble("candidate", text);
  if (typed) field.value = "";
  const dots = typing();
  try {
    const reply = await request(`${path()}/messages`, { text });
    dots.remove();
    bubble("agent", reply.text);
    show(reply);
    if (voice) speak();
  } catch {
    dots.remove();
    error(labels.sendFailed);
    if (typed && !field.value) field.value = text;
    if (voice) listen();
  } finally {
    setBusy(false);
    // The tapped city button is gone: keep focus in the chat, not on <body>.
    // Not while talking: on a phone, focus opens the keyboard.
    if (!typed && !voice) field.focus();
  }
}

// Voice (decision 003): the candidate's turn ends after SILENCE_MS of quiet,
// talking over Leo stops him (barge-in), and nothing is heard while a turn runs,
// so one conversation never runs two turns at once.
// shortcut: energy-based voice detection, so steady noise can start or hold a
// turn; Silero VAD (a new dependency) if real rooms need it.
const FRAME_MS = 20;
const SPEECH_MS = 100; // loud this long starts the candidate's turn
const BARGE_IN_MS = 300; // longer over Leo, so leftover echo does not stop him
const SILENCE_MS = 800; // quiet this long ends it
const MARGIN_DB = 15; // loud is this far over the noise floor
const MIN_DB = -50; // and over this, as noise suppression can leave near silence
const RISE_DB = 0.02; // per frame: the floor follows new noise, not speech
const RESTART_MS = 5000; // a recording this long without speech starts over

let voice = null; // microphone, recorder and playback while voice is on

function setState(state) {
  if (voice) voice.state = state;
  talk.setAttribute("aria-pressed", String(voice !== null));
  voiceStatus.dataset.state = state;
  voiceStatus.textContent = voice ? labels[state] : "";
}

async function startVoice() {
  // In the tap itself: Safari keeps an AudioContext made later silent.
  const context = new AudioContext();
  const type = ["audio/webm", "audio/mp4"].find((t) =>
    window.MediaRecorder?.isTypeSupported(t),
  );
  talk.disabled = true;
  try {
    if (!type) throw new Error("no recorder");
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    // A microphone unplugged or revoked mid-chat ends voice like any failure.
    stream.getTracks()[0].addEventListener("ended", voiceFailed);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);
    const now = performance.now();
    voice = {
      context,
      stream,
      analyser,
      type,
      samples: new Float32Array(analyser.fftSize),
      floor: MIN_DB,
      lastLoud: now,
      lastQuiet: now,
      talking: false,
      timer: setInterval(hear, FRAME_MS),
    };
  } catch {
    context.close();
    return error(labels.micFailed);
  } finally {
    talk.disabled = false;
  }
  setState("thinking");
  try {
    const files = Object.values(LABELS).flatMap((l) => l.acks);
    const buffers = await Promise.all(files.map(decode));
    voice.acks = new Map(files.map((file, i) => [file, buffers[i]]));
  } catch {
    return voiceFailed();
  }
  if (!busy) speak(); // else the running turn speaks its reply
}

function stopVoice() {
  clearInterval(voice.timer);
  drop();
  voice.reply?.stop();
  for (const track of voice.stream.getTracks()) track.stop();
  voice.context.close();
  voice = null;
  setState("off");
}

function voiceFailed() {
  if (!voice) return; // switched off meanwhile
  stopVoice();
  error(labels.voiceFailed);
}

async function decode(url) {
  const { context } = voice;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return context.decodeAudioData(await response.arrayBuffer());
}

function play(buffer, ended, offset = 0) {
  const source = voice.context.createBufferSource();
  source.buffer = buffer;
  source.connect(voice.context.destination);
  source.onended = ended;
  source.start(0, offset);
  return source;
}

function record() {
  drop();
  const chunks = [];
  const recorder = new MediaRecorder(voice.stream, { mimeType: voice.type });
  recorder.ondataavailable = (event) => chunks.push(event.data);
  recorder.start();
  Object.assign(voice, { recorder, chunks, since: performance.now() });
}

function drop() {
  if (voice.recorder?.state === "recording") voice.recorder.stop();
  voice.recorder = null;
}

function recording() {
  const { recorder, chunks } = voice;
  voice.recorder = null;
  return new Promise((resolve) => {
    recorder.onstop = () => resolve(new Blob(chunks, { type: recorder.mimeType }));
    recorder.stop();
  });
}

function listen() {
  if (!voice.talking) record(); // a fresh one: Leo's leftover echo stays out
  setState("listening");
}

// A turn runs: stop Leo and drop what the microphone has.
function hush() {
  voice.reply?.stop();
  drop();
  voice.talking = false;
  voice.cut = undefined;
  setState("thinking");
}

async function speak() {
  setState("thinking");
  let buffer;
  try {
    buffer = await decode(`${path()}/speech`);
    await voice.ack; // the acknowledgement plays to its end
  } catch {
    return voiceFailed();
  }
  if (!voice || busy) return; // off, or a newer turn will speak
  say(buffer, 0);
}

// Leo's reply from offset seconds on.
function say(buffer, offset) {
  record(); // from the start, so a barge-in keeps its first words
  const ended = () => voice?.state === "speaking" && listen();
  voice.reply = play(buffer, ended, offset);
  voice.started = voice.context.currentTime - offset;
  setState("speaking");
}

function hear() {
  const { state, analyser, samples } = voice;
  if (state !== "listening" && state !== "speaking") return;
  analyser.getFloatTimeDomainData(samples);
  const power = samples.reduce((sum, s) => sum + s * s, 0) / samples.length;
  const db = 10 * Math.log10(power || 1e-10);
  voice.floor = Math.min(db, voice.floor + RISE_DB);
  const loud = db > Math.max(voice.floor + MARGIN_DB, MIN_DB);
  const now = performance.now();
  if (loud) voice.lastLoud = now;
  else voice.lastQuiet = now;
  const level = Math.min(1, Math.max(0, (db - MIN_DB) / 30));
  voiceStatus.style.setProperty("--level", level);
  const starts = state === "speaking" ? BARGE_IN_MS : SPEECH_MS;
  if (!voice.talking && now - voice.lastQuiet >= starts) {
    voice.talking = true;
    if (state === "speaking") {
      // Barge-in. State first: stop()'s ended event must keep the recording.
      setState("listening");
      voice.reply.stop();
      voice.cut = voice.context.currentTime - voice.started;
    }
  } else if (voice.talking && now - voice.lastLoud >= SILENCE_MS) {
    endOfSpeech();
  } else if (!voice.talking && !loud && now - voice.since >= RESTART_MS) {
    record();
  }
}

async function endOfSpeech() {
  voice.talking = false;
  const { cut } = voice; // where a barge-in stopped Leo, if one did
  voice.cut = undefined;
  const { acks } = labels;
  const ack = voice.acks.get(acks[Math.floor(Math.random() * acks.length)]);
  voice.ack = new Promise((resolve) => play(ack, resolve));
  setState("thinking");
  const audio = await recording();
  let text;
  try {
    const response = await fetch(`${path()}/transcription`, {
      method: "POST",
      headers: { "Content-Type": audio.type },
      body: audio,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    ({ text } = await response.json());
  } catch {
    return voiceFailed();
  }
  if (text.trim()) return submit(text, false);
  if (!voice) return;
  if (cut === undefined) return listen(); // a noise, not words
  // No words cut Leo off: on speakers, his own echo can. He goes on.
  await voice.ack;
  if (voice) say(voice.reply.buffer, cut);
}

talk.addEventListener("click", () => (voice ? stopVoice() : startVoice()));

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
