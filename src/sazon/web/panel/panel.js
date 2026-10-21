// Recruiter panel: the work queue and one candidate's detail. Names, the
// transcript, questions and AI notes are text the candidate wrote or
// influenced: everything is set with textContent, never parsed as HTML.

const VIEWS = {
  queue: ["qualified", "needs_review"],
  disqualified: ["disqualified"],
  withdrawn: ["withdrawn"],
  abandoned: ["abandoned"],
};
// Option order only: the server checks every value (engine.RecruiterStatus).
const STATUSES = ["pending", "contacted", "hired", "rejected", "showed_up", "no_show"];
const COUNTRIES = { ES: "Spain", MX: "Mexico" };
const LANGUAGES = { es: "Spanish", en: "English" };
const narrow = matchMedia("(max-width: 759px)");

const $ = (id) => document.getElementById(id);

let rows = [];
let view = "queue";
let current = null; // the open candidate's detail

const human = (value) => value.replaceAll("_", " ");
const sentence = (text) => text.charAt(0).toUpperCase() + text.slice(1);
const when = (iso) =>
  new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, body) {
  const options =
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        };
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function error(text) {
  $("error").textContent = text;
  $("error").hidden = !text;
}

function badge(candidate) {
  // A reopened candidate's reason belongs to the screening's outcome.
  const reason = candidate.reason && !candidate.reopened_at ? ` · ${human(candidate.reason)}` : "";
  return el("span", `badge ${candidate.outcome}`, human(candidate.outcome) + reason);
}

function place(candidate) {
  if (candidate.zone === null) return "No zone given";
  if (candidate.city === null) return `${candidate.zone} (not covered)`;
  const city = candidate.city === candidate.zone ? candidate.city : `${candidate.zone} → ${candidate.city}`;
  return `${city}, ${COUNTRIES[candidate.country] ?? candidate.country}`;
}

// The name comes after the knockout questions (decision 005), so many have none.
function displayName(candidate) {
  if (candidate.name) return candidate.name;
  return candidate.flagged.includes("full_name") ? "Unnamed · name flagged" : "Unnamed · left before giving a name";
}

// The row and the detail date the screening, not the hiring status.
function stamp(candidate) {
  const label = candidate.outcome === "abandoned" ? "last message" : "closed";
  return `${label} ${when(candidate.at)}`;
}

function flags(candidate) {
  return [
    ...candidate.flagged.map((field) => `flagged: ${human(field)}`),
    ...(candidate.wrote_after_close ? ["wrote after close"] : []),
    ...(candidate.reopened_at ? ["reopened"] : []),
  ];
}

// Zone filter values: "country:ES", "city:Madrid", "uncovered" or "missing".
function inZone(candidate, value) {
  const [kind, name] = value.split(":");
  if (kind === "country") return candidate.country === name;
  if (kind === "city") return candidate.city === name;
  if (kind === "uncovered") return candidate.zone !== null && candidate.city === null;
  if (kind === "missing") return candidate.zone === null;
  return true;
}

function fillZones() {
  const select = $("zone");
  const chosen = select.value;
  const cities = {};
  for (const row of rows) if (row.city) (cities[row.country] ??= new Set()).add(row.city);
  select.replaceChildren(new Option("All zones", ""));
  for (const country of Object.keys(cities).sort()) {
    const group = el("optgroup");
    group.label = COUNTRIES[country] ?? country;
    group.append(new Option(`All of ${group.label}`, `country:${country}`));
    for (const city of [...cities[country]].sort()) group.append(new Option(city, `city:${city}`));
    select.append(group);
  }
  if (rows.some((row) => inZone(row, "uncovered"))) select.append(new Option("Not covered", "uncovered"));
  if (rows.some((row) => inZone(row, "missing"))) select.append(new Option("No zone given", "missing"));
  select.value = [...select.options].some((option) => option.value === chosen) ? chosen : "";
}

function renderViews() {
  for (const button of $("views").querySelectorAll("button")) {
    const inView = rows.filter((row) => VIEWS[button.dataset.view].includes(row.outcome));
    const late = inView.filter((row) => row.wrote_after_close).length;
    button.setAttribute("aria-pressed", String(button.dataset.view === view));
    button.querySelector(".count").textContent = inView.length.toLocaleString("en-GB");
    button.querySelector(".late").textContent = late ? `${late} wrote after close` : "";
  }
  $("outcome-filter").hidden = view !== "queue";
}

function rowItem(row) {
  const button = el("button", "row");
  button.type = "button";
  button.dataset.id = row.id;
  const top = el("span", "row-top");
  top.append(el("span", "name", displayName(row)), badge(row));
  const state = row.outcome === "abandoned" ? `stopped at ${human(row.stopped)}` : `hiring: ${human(row.status)}`;
  const chips = el("span", "flags");
  chips.append(...flags(row).map((text) => el("span", "flag", text)));
  // The place may wrap; the status and the date stay whole.
  const meta = el("span", "meta", place(row));
  for (const part of [state, stamp(row)]) meta.append(" · ", el("span", "keep", part));
  button.append(top, meta, chips);
  button.addEventListener("click", () => open(row.id));
  const item = el("li");
  item.append(button);
  return item;
}

function renderList() {
  const outcome = view === "queue" ? $("outcome").value : "";
  const shown = rows.filter(
    (row) =>
      VIEWS[view].includes(row.outcome) &&
      (!outcome || row.outcome === outcome) &&
      inZone(row, $("zone").value),
  );
  $("rows").replaceChildren(...shown.map(rowItem));
  $("empty").hidden = shown.length > 0;
  $("count").textContent = `${shown.length} ${shown.length === 1 ? "candidate" : "candidates"}`;
  if (!current) $("pick").hidden = shown.length === 0; // nothing to select
  markCurrent();
}

// Marks the open row in place: re-rendering the list would drop the focus.
function markCurrent() {
  for (const button of $("rows").querySelectorAll(".row")) {
    if (button.dataset.id === current?.candidate.id) button.setAttribute("aria-current", "true");
    else button.removeAttribute("aria-current");
  }
}

function notices(detail) {
  const candidate = detail.candidate;
  const list = [];
  if (candidate.flagged.length)
    list.push(["warn", `Flagged for review: ${candidate.flagged.map(human).join(", ")}. No valid answer after three tries.`]);
  if (candidate.wrote_after_close)
    list.push(["warn", "Wrote after the screening closed. Read the end of the transcript."]);
  if (candidate.reopened_at)
    list.push(["info", `Reopened for review on ${when(candidate.reopened_at)}. The summary keeps the screening's outcome.`]);
  if (candidate.outcome === "abandoned")
    list.push(["info", `Stopped replying at the ${human(candidate.stopped)} question.`]);
  if (detail.pool)
    list.push(["info", `Wants to hear if we open in ${detail.pool.city} (consent until ${detail.pool.expires_on}).`]);
  return list.map(([kind, text]) => el("p", `notice ${kind}`, text));
}

function renderJson(fields, flagged) {
  const pre = $("json");
  pre.replaceChildren();
  for (const line of JSON.stringify(fields, null, 2).split("\n")) {
    const key = line.match(/^ {2}"(\w+)":/)?.[1];
    if (flagged.includes(key)) {
      const mark = el("mark", "", line);
      mark.append(el("span", "visually-hidden", " (flagged)"));
      pre.append(mark, "\n");
    } else {
      pre.append(`${line}\n`);
    }
  }
}

const day = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
const clock = (iso) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

// The date only on the first line and when it changes.
function transcriptLine(line, index, lines) {
  const item = el("li", `line ${line.role}`);
  const sameDay = index > 0 && day(lines[index - 1].at) === day(line.at);
  const time = el("time", "", sameDay ? clock(line.at) : `${day(line.at)} ${clock(line.at)}`);
  time.dateTime = line.at;
  const who = el("span", "who", line.role === "agent" ? "Leo (AI)" : "Candidate");
  item.append(time, who, el("p", "", line.text));
  return item;
}

function show(detail, focus) {
  current = detail;
  const candidate = detail.candidate;
  $("detail").hidden = false;
  $("pick").hidden = true;
  document.body.dataset.view = "detail";
  $("detail-name").textContent = displayName(candidate);
  $("detail-badge").replaceChildren(badge(candidate));
  $("detail-facts").textContent = [
    place(candidate),
    LANGUAGES[detail.language] ?? detail.language,
    stamp(candidate),
  ].join(" · ");
  $("notices").replaceChildren(...notices(detail));
  $("status").value = candidate.status;
  $("reopen").hidden = candidate.outcome !== "disqualified";
  $("summary").textContent = detail.summary;
  const notes = detail.notes ?? [];
  $("notes").replaceChildren(...notes.map((note) => el("li", "", note)));
  $("no-notes").textContent =
    candidate.outcome === "abandoned"
      ? "None yet: the note is written when a screening closes."
      : detail.notes === null
        ? "Unavailable: the model call failed when the screening closed."
        : "None: the candidate wrote nothing the fields do not hold.";
  $("no-notes").hidden = notes.length > 0;
  $("questions").replaceChildren(...detail.questions.map((question) => el("li", "", question)));
  $("no-questions").hidden = detail.questions.length > 0;
  renderJson(detail.fields, candidate.flagged);
  $("transcript").replaceChildren(...detail.transcript.map(transcriptLine));
  if (focus) $("detail-name").focus();
}

async function load() {
  try {
    rows = await api("/panel/candidates");
  } catch {
    return error("Couldn't load the candidates. Reload the page.");
  }
  error("");
  fillZones();
  renderViews();
  renderList();
}

async function open(id) {
  try {
    const detail = await api(`/panel/candidates/${encodeURIComponent(id)}`);
    error("");
    show(detail, narrow.matches);
    markCurrent();
  } catch {
    error("Couldn't load this candidate. Try again.");
  }
}

async function write(action, body, failed) {
  const path = `/panel/candidates/${encodeURIComponent(current.candidate.id)}/${action}`;
  try {
    show(await api(path, body), false);
    error("");
    await load(); // the row may move to another list
  } catch {
    show(current, false);
    error(failed);
  }
}

for (const status of STATUSES) $("status").append(new Option(sentence(human(status)), status));

$("status").addEventListener("change", async (event) => {
  event.target.disabled = true;
  await write("status", { status: event.target.value }, "Couldn't save the status. Try again.");
  event.target.disabled = false;
});

$("reopen").addEventListener("click", async () => {
  if (!confirm("Reopen this candidate? They move to the queue as needs review.")) return;
  await write("reopen", {}, "Couldn't reopen the candidate. Try again.");
});

for (const button of $("views").querySelectorAll("button")) {
  button.addEventListener("click", () => {
    view = button.dataset.view;
    renderViews();
    renderList();
  });
}
$("outcome").addEventListener("change", renderList);
$("zone").addEventListener("change", renderList);

$("back").addEventListener("click", () => {
  document.body.dataset.view = "list";
  document.querySelector('.row[aria-current="true"]')?.focus();
});

$("refresh").addEventListener("click", async () => {
  await load();
  if (current) await open(current.candidate.id);
});

load();
