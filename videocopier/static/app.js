const form = document.getElementById("form");
const logEl = document.getElementById("log");
const progress = document.getElementById("progress");
const result = document.getElementById("result");
const missing = document.getElementById("missing");
const buildBtn = document.getElementById("build");
const boardPill = document.getElementById("board-pill");
const clipGrid = document.getElementById("clip-grid");
const clipStatus = document.getElementById("clip-status");

const review = document.getElementById("review");
const captionEditor = document.getElementById("caption-editor");
const approveBtn = document.getElementById("approve");
const tlLanes = document.getElementById("tl-lanes");
const tlRuler = document.getElementById("tl-ruler");

const state = {
  clips: [],
  boardSlots: [],
  clients: [],
  boardId: "",
  clientId: "",
  jobId: "",
  draft: [],
  duration: 22,
  selected: 0,
};

async function api(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Sign in required");
  }
  return res;
}

function clientName() {
  return document.getElementById("client").selectedOptions[0]?.text || "the client";
}

function selectedClips() {
  return state.clips.filter((c) => c.selected && c.path);
}

function renderClips() {
  const n = selectedClips().length;
  clipStatus.textContent = state.clips.length
    ? `${n} selected · tap a clip to include or skip`
    : "No clips yet.";
  clipGrid.innerHTML = state.clips
    .map((clip) => {
      let badge = "Shaky";
      let kind = "warn";
      if (clip.captioned) {
        badge = "Has captions";
        kind = "warn";
      } else if (clip.stable) {
        badge = "Stable";
        kind = "ok";
      }
      const on = clip.selected ? "on" : "";
      return `<button type="button" class="clip-card ${on}" data-id="${clip.id}">
        <img src="${clip.thumb}" alt="" />
        <span class="badge ${kind}">${badge}</span>
        <span class="name">${clip.name}</span>
        <span class="meta">${clip.duration}s · ${clip.motion}</span>
      </button>`;
    })
    .join("");
}

clipGrid.addEventListener("click", (e) => {
  const card = e.target.closest(".clip-card");
  if (!card) return;
  const clip = state.clips.find((c) => c.id === card.dataset.id);
  if (!clip) return;
  clip.selected = !clip.selected;
  renderClips();
});

document.getElementById("pick-footage-video").addEventListener("click", () => {
  document.getElementById("footage-files").click();
});

document.getElementById("footage-files").addEventListener("change", async (e) => {
  const files = [...(e.target.files || [])];
  e.target.value = "";
  if (!files.length) return;
  const btn = document.getElementById("pick-footage-video");
  btn.disabled = true;
  btn.textContent = "Reading clips…";
  clipStatus.textContent = "Checking which takes are stable…";
  try {
    const body = new FormData();
    files.forEach((file) => body.append("footage", file, file.name));
    const res = await api("/api/clips/inspect", { method: "POST", body });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not read those clips");
    (data.clips || []).forEach((clip) => {
      if (state.clips.some((c) => c.name === clip.name && c.duration === clip.duration)) return;
      state.clips.push(clip);
    });
    renderClips();
  } catch (err) {
    clipStatus.textContent = err.message || "Could not read those clips";
  } finally {
    btn.disabled = false;
    btn.textContent = "Add videos";
  }
});

function hidePreview() {
  document.getElementById("format-preview").classList.add("hidden");
  const orig = document.getElementById("original-player");
  orig.pause();
  orig.removeAttribute("src");
  orig.load();
}

function playOriginal(src, status) {
  const orig = document.getElementById("original-player");
  const note = document.getElementById("original-status");
  orig.src = src;
  orig.load();
  note.textContent = status || `Layout only. Captions will be rewritten for ${clientName()}.`;
}

function renderBoard() {
  const q = document.getElementById("board-search").value.trim().toLowerCase();
  const list = document.getElementById("board-list");
  const statusEl = document.getElementById("board-status");
  if (!state.clientId) {
    list.innerHTML = "";
    statusEl.textContent = "Pick a client first.";
    hidePreview();
    return;
  }
  const rows = state.boardSlots.filter((slot) => {
    if (slot.clientId !== state.clientId) return false;
    if (
      q &&
      !(slot.hook || "").toLowerCase().includes(q) &&
      !(slot.caption || "").toLowerCase().includes(q)
    ) {
      return false;
    }
    return true;
  });
  statusEl.textContent = `${rows.length} format${rows.length === 1 ? "" : "s"}`;
  list.innerHTML = rows
    .slice(0, 80)
    .map((slot) => {
      const thumb = slot.thumb
        ? `<img src="/api/board/thumb?src=${encodeURIComponent(slot.thumb)}" alt="" />`
        : `<img alt="" />`;
      return `<button type="button" class="board-item ${slot.id === state.boardId ? "on" : ""}" data-id="${slot.id}">
        ${thumb}
        <span><strong>${slot.hook || "Untitled"}</strong><span class="meta">#${slot.slotNumber || "?"}</span></span>
      </button>`;
    })
    .join("");
  if (!rows.length) {
    list.innerHTML = `<p class="hint">No approved formats for this client.</p>`;
  }
}

document.getElementById("board-list").addEventListener("click", (e) => {
  const item = e.target.closest(".board-item");
  if (!item) return;
  state.boardId = item.dataset.id;
  renderBoard();
  const slot = state.boardSlots.find((s) => s.id === state.boardId);
  document.getElementById("format-preview").classList.remove("hidden");
  playOriginal(
    `/api/board/slot/${state.boardId}/video`,
    slot ? `${slot.hook || "This format"} — words get rewritten for ${clientName()}.` : ""
  );
});

document.getElementById("board-search").addEventListener("input", renderBoard);

document.getElementById("client").addEventListener("change", (e) => {
  state.clientId = e.target.value;
  state.boardId = "";
  hidePreview();
  renderBoard();
  buildBtn.textContent = state.clientId ? `Read words for ${clientName()}` : "Read words";
});

async function loadBoard() {
  const statusEl = document.getElementById("board-status");
  const select = document.getElementById("client");
  try {
    const health = await api("/api/board/status").then((r) => r.json());
    if (!health.ok) {
      boardPill.textContent = "Board: offline";
      statusEl.textContent = health.error || "Could not reach the Board.";
      select.innerHTML = `<option value="">Board offline</option>`;
      return;
    }
    boardPill.textContent = `Board: ${health.user?.name || health.user?.email || "connected"}`;
    boardPill.classList.add("ok");
    const data = await api("/api/board/approved").then((r) => r.json());
    if (!data.ok) throw new Error(data.detail || "Could not load approved videos");
    state.boardSlots = data.slots || [];
    state.clients = data.clients || [];
    select.innerHTML =
      `<option value="">Select a client</option>` +
      state.clients.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
    const melo = state.clients.find((c) => /melomelo/i.test(c.name));
    if (melo) {
      select.value = melo.id;
      state.clientId = melo.id;
      buildBtn.textContent = `Read words for ${melo.name}`;
    }
    renderBoard();
  } catch (err) {
    boardPill.textContent = "Board: offline";
    statusEl.textContent = err.message || "Could not reach the Board.";
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  result.classList.add("hidden");
  review.classList.add("hidden");
  progress.classList.remove("hidden");
  logEl.innerHTML = "";
  buildBtn.disabled = true;

  const picked = selectedClips();
  if (!state.clientId) {
    addLog("Pick the client.", true);
    buildBtn.disabled = false;
    return;
  }
  if (!state.boardId) {
    addLog("Pick the format video.", true);
    buildBtn.disabled = false;
    return;
  }
  if (!picked.length) {
    addLog("Pick at least one stable clip.", true);
    buildBtn.disabled = false;
    return;
  }

  try {
    const body = new FormData();
    body.append("reference", `board:${state.boardId}`);
    body.append("client_id", state.clientId);
    body.append("caption_mode", "client");
    picked.forEach((clip) => body.append("footage", clip.path));
    addLog(`Using ${picked.length} clip${picked.length === 1 ? "" : "s"}…`);
    const res = await api("/api/jobs", { method: "POST", body });
    const job = await res.json();
    if (!res.ok) throw new Error(job.detail || "Could not start job");
    state.jobId = job.id;
    poll(job.id);
  } catch (err) {
    addLog(String(err.message || err), true);
    buildBtn.disabled = false;
  }
});

function addLog(text, err) {
  const li = document.createElement("li");
  li.textContent = text;
  if (err) li.className = "err";
  logEl.appendChild(li);
}

async function poll(id) {
  const seen = new Set();
  const tick = async () => {
    const job = await api(`/api/jobs/${id}`).then((r) => r.json());
    for (const line of job.log || []) {
      if (!seen.has(line)) {
        seen.add(line);
        addLog(line, line.startsWith("Error"));
      }
    }
    if (job.status === "review") {
      buildBtn.disabled = false;
      showReview(job);
      return;
    }
    if (job.status === "done") {
      buildBtn.disabled = false;
      approveBtn.disabled = false;
      showResult(id, job);
      return;
    }
    if (job.status === "error") {
      buildBtn.disabled = false;
      approveBtn.disabled = false;
      addLog(job.error || "Job failed", true);
      if ((job.draft_captions || []).length) showReview(job);
      return;
    }
    setTimeout(tick, 1000);
  };
  tick();
}

function esc(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtTime(t) {
  const n = Number(t);
  return Number.isFinite(n) ? n.toFixed(1) : "0.0";
}

function showReview(job) {
  review.classList.remove("hidden");
  result.classList.add("hidden");
  const source = job.source_captions || [];
  const ocrBox = document.getElementById("ocr-read");
  const ocrLines = document.getElementById("ocr-lines");
  if (source.length) {
    ocrBox.classList.remove("hidden");
    const shown = source.slice(0, 24);
    ocrLines.innerHTML =
      shown
        .map(
          (c) =>
            `<li>${fmtTime(c.start)}–${fmtTime(c.end)}s · ${esc(c.text).replace(/\n/g, " / ")}</li>`
        )
        .join("") +
      (source.length > 24 ? `<li>…${source.length - 24} more OCR crumbs</li>` : "");
  } else {
    ocrBox.classList.add("hidden");
    ocrLines.innerHTML = "";
  }
  state.draft = (job.draft_captions || []).length
    ? job.draft_captions.map((c) => ({ ...c }))
    : [
        {
          text: "",
          start: 0,
          end: 3,
          face: "classic",
          y_ratio: 0.22,
          width_ratio: 0,
          size_ratio: 0,
          kind: "overlay",
        },
      ];
  const ends = state.draft.map((c) => Number(c.end) || 0);
  state.duration = Math.max(Number(job.duration) || 0, ...ends, 8);
  state.selected = 0;
  renderTimeline();
  renderScript();
  review.scrollIntoView({ behavior: "smooth", block: "start" });
}

function packLanes(cards) {
  const ends = [];
  const laneOf = [];
  cards
    .map((c, i) => ({ i, start: Number(c.start) || 0, end: Number(c.end) || 0 }))
    .sort((a, b) => a.start - b.start)
    .forEach((c) => {
      let lane = ends.findIndex((end) => c.start >= end - 0.05);
      if (lane < 0) {
        lane = ends.length;
        ends.push(0);
      }
      ends[lane] = Math.max(ends[lane], c.end);
      laneOf[c.i] = lane;
    });
  return { count: Math.max(ends.length, 1), laneOf };
}

function renderTimeline() {
  const dur = Math.max(state.duration, 0.1);
  const step = dur > 40 ? 5 : dur > 20 ? 2 : 1;
  const ticks = [];
  for (let t = 0; t <= dur + 0.001; t += step) ticks.push(t);
  if (ticks[ticks.length - 1] < dur - 0.05) ticks.push(dur);
  tlRuler.innerHTML = ticks
    .map((t) => `<span class="tl-tick" style="left:${(t / dur) * 100}%">${t.toFixed(t % 1 ? 1 : 0)}s</span>`)
    .join("");
  const { count, laneOf } = packLanes(state.draft);
  const lanes = Array.from({ length: count }, () => "");
  state.draft.forEach((c, i) => {
    const start = Math.max(0, Number(c.start) || 0);
    const end = Math.max(start + 0.4, Number(c.end) || start + 0.4);
    const left = (start / dur) * 100;
    const width = Math.max(((end - start) / dur) * 100, 2.2);
    const label = (c.text || "empty").replace(/\n/g, " / ");
    const on = i === state.selected ? " on" : "";
    const face = c.face === "box" ? " box" : "";
    const lane = laneOf[i] || 0;
    lanes[lane] += `<button type="button" class="tl-clip${face}${on}" data-i="${i}" style="left:${left}%;width:${width}%" title="${fmtTime(start)}–${fmtTime(end)}s">
      <span class="tl-handle left" data-edge="left"></span>${esc(label)}
      <span class="tl-handle right" data-edge="right"></span>
    </button>`;
  });
  tlLanes.innerHTML = lanes.map((html) => `<div class="tl-lane">${html}</div>`).join("");
  const card = state.draft[state.selected];
  const note = document.getElementById("tl-selected");
  if (card) {
    const preview = (card.text || "(empty)").replace(/\n/g, " / ").slice(0, 80);
    note.textContent = `${fmtTime(card.start)}–${fmtTime(card.end)}s · ${preview}`;
  } else {
    note.textContent = "Add a card to the timeline.";
  }
}

function renderScript() {
  captionEditor.innerHTML = state.draft
    .map((c, i) => {
      const face = c.face === "box" ? "box" : "classic";
      const on = i === state.selected ? " on" : "";
      return `<div class="script-row${on}" data-i="${i}">
        <div class="script-times">
          <label>In<input type="number" step="0.1" min="0" class="t-start" value="${fmtTime(c.start)}"></label>
          <label>Out<input type="number" step="0.1" min="0" class="t-end" value="${fmtTime(c.end)}"></label>
        </div>
        <textarea class="t-text" rows="3">${esc(c.text)}</textarea>
        <div class="script-side">
          <select class="t-face">
            <option value="classic"${face === "classic" ? " selected" : ""}>Classic</option>
            <option value="box"${face === "box" ? " selected" : ""}>Box</option>
          </select>
          <button type="button" class="remove">Remove</button>
        </div>
      </div>`;
    })
    .join("");
}

function highlight() {
  [...tlLanes.querySelectorAll(".tl-clip")].forEach((el) => {
    el.classList.toggle("on", Number(el.dataset.i) === state.selected);
  });
  [...captionEditor.querySelectorAll(".script-row")].forEach((el) => {
    el.classList.toggle("on", Number(el.dataset.i) === state.selected);
  });
  const card = state.draft[state.selected];
  const note = document.getElementById("tl-selected");
  if (card) {
    note.textContent = `${fmtTime(card.start)}–${fmtTime(card.end)}s · ${(card.text || "(empty)").replace(/\n/g, " / ").slice(0, 80)}`;
  }
}

function selectCard(i) {
  state.selected = i;
  highlight();
  const row = captionEditor.querySelector(`.script-row[data-i="${i}"]`);
  if (row) {
    row.scrollIntoView({ behavior: "smooth", block: "nearest" });
    const area = row.querySelector(".t-text");
    if (area && document.activeElement !== area) area.focus();
  }
}

function syncDraftFromDom() {
  [...captionEditor.querySelectorAll(".script-row")].forEach((row) => {
    const i = Number(row.dataset.i);
    const card = state.draft[i];
    if (!card) return;
    const start = Number(row.querySelector(".t-start").value);
    const end = Number(row.querySelector(".t-end").value);
    card.start = Number.isFinite(start) ? start : 0;
    card.end = Number.isFinite(end) ? Math.max(end, card.start + 0.4) : card.start + 1;
    card.text = row.querySelector(".t-text").value;
    card.face = row.querySelector(".t-face").value;
    card.kind = "overlay";
  });
}

captionEditor.addEventListener("click", (e) => {
  const row = e.target.closest(".script-row");
  if (!row) return;
  const i = Number(row.dataset.i);
  if (e.target.closest(".remove")) {
    syncDraftFromDom();
    state.draft.splice(i, 1);
    state.selected = Math.min(i, Math.max(state.draft.length - 1, 0));
    renderTimeline();
    renderScript();
    return;
  }
  selectCard(i);
});

captionEditor.addEventListener("input", (e) => {
  const row = e.target.closest(".script-row");
  if (!row) return;
  syncDraftFromDom();
  if (e.target.classList.contains("t-start") || e.target.classList.contains("t-end") || e.target.classList.contains("t-face")) {
    renderTimeline();
  } else {
    highlight();
  }
});

document.getElementById("add-card").addEventListener("click", () => {
  syncDraftFromDom();
  const last = state.draft[state.draft.length - 1];
  const start = last ? Number(last.end) || 0 : 0;
  state.draft.push({
    text: "",
    start,
    end: Math.min(start + 2, state.duration || start + 2),
    face: last?.face || "classic",
    y_ratio: last?.y_ratio ?? 0.22,
    width_ratio: last?.width_ratio ?? 0,
    size_ratio: last?.size_ratio ?? 0,
    kind: "overlay",
  });
  state.selected = state.draft.length - 1;
  renderTimeline();
  renderScript();
});

let drag = null;

tlLanes.addEventListener("pointerdown", (e) => {
  const clip = e.target.closest(".tl-clip");
  if (!clip) return;
  syncDraftFromDom();
  const i = Number(clip.dataset.i);
  state.selected = i;
  highlight();
  const card = state.draft[i];
  const track = tlLanes.getBoundingClientRect();
  const handle = e.target.closest(".tl-handle");
  drag = {
    i,
    mode: handle ? handle.dataset.edge : "move",
    x0: e.clientX,
    start: Number(card.start) || 0,
    end: Number(card.end) || 0,
    width: track.width,
  };
  clip.setPointerCapture(e.pointerId);
  e.preventDefault();
});

tlLanes.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const dt = ((e.clientX - drag.x0) / drag.width) * state.duration;
  const card = state.draft[drag.i];
  const span = Math.max(drag.end - drag.start, 0.4);
  if (drag.mode === "move") {
    let start = Math.max(0, drag.start + dt);
    let end = start + span;
    if (end > state.duration) {
      end = state.duration;
      start = Math.max(0, end - span);
    }
    card.start = Math.round(start * 10) / 10;
    card.end = Math.round(end * 10) / 10;
  } else if (drag.mode === "left") {
    card.start = Math.round(Math.max(0, Math.min(drag.end - 0.4, drag.start + dt)) * 10) / 10;
  } else {
    card.end = Math.round(Math.min(state.duration, Math.max(drag.start + 0.4, drag.end + dt)) * 10) / 10;
  }
  const clip = tlLanes.querySelector(`.tl-clip[data-i="${drag.i}"]`);
  if (clip) {
    const dur = Math.max(state.duration, 0.1);
    const start = Math.max(0, card.start);
    const end = Math.max(start + 0.4, card.end);
    clip.style.left = `${(start / dur) * 100}%`;
    clip.style.width = `${Math.max(((end - start) / dur) * 100, 2.2)}%`;
    clip.title = `${fmtTime(start)}–${fmtTime(end)}s`;
  }
  const row = captionEditor.querySelector(`.script-row[data-i="${drag.i}"]`);
  if (row) {
    row.querySelector(".t-start").value = fmtTime(card.start);
    row.querySelector(".t-end").value = fmtTime(card.end);
  }
  const note = document.getElementById("tl-selected");
  note.textContent = `${fmtTime(card.start)}–${fmtTime(card.end)}s · ${(card.text || "(empty)").replace(/\n/g, " / ").slice(0, 80)}`;
});

function endDrag(e) {
  const moved = drag && Math.abs(e.clientX - drag.x0) > 4;
  const i = drag ? drag.i : null;
  drag = null;
  if (i == null) return;
  renderTimeline();
  if (!moved) selectCard(i);
}

tlLanes.addEventListener("pointerup", endDrag);
tlLanes.addEventListener("pointercancel", () => {
  drag = null;
});

approveBtn.addEventListener("click", async () => {
  syncDraftFromDom();
  const captions = state.draft.filter((c) => (c.text || "").trim());
  if (!captions.length) {
    addLog("Write at least one line before burning.", true);
    return;
  }
  if (!state.jobId) {
    addLog("No remake waiting for approval.", true);
    return;
  }
  approveBtn.disabled = true;
  review.classList.add("hidden");
  progress.classList.remove("hidden");
  addLog("Approved — burning captions…");
  try {
    const res = await api(`/api/jobs/${state.jobId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ captions }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not approve");
    poll(state.jobId);
  } catch (err) {
    approveBtn.disabled = false;
    review.classList.remove("hidden");
    addLog(String(err.message || err), true);
  }
});

function showResult(id, job) {
  review.classList.add("hidden");
  result.classList.remove("hidden");
  const mp4 = `/api/jobs/${id}/file/mp4?t=${Date.now()}`;
  document.getElementById("player").src = mp4;
  const compare = document.getElementById("compare-original");
  if (state.boardId) {
    compare.src = `/api/board/slot/${state.boardId}/video`;
  }
  document.getElementById("dl-mp4").href = mp4;
  document.getElementById("dl-xml").href = `/api/jobs/${id}/file/xml`;
  document.getElementById("dl-json").href = `/api/jobs/${id}/file/cutlist`;
  if (job.unfilled?.length) {
    missing.classList.remove("hidden");
    missing.querySelector("ul").innerHTML = job.unfilled.map((s) => `<li>${s}</li>`).join("");
  } else {
    missing.classList.add("hidden");
  }
}

document.getElementById("signout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

api("/api/me")
  .then((r) => r.json())
  .then((me) => {
    if (me.email) document.getElementById("user-pill").textContent = me.email;
  })
  .catch(() => {});

loadBoard();
renderClips();

api("/api/jobs/latest?status=review")
  .then((r) => r.json())
  .then((data) => {
    const job = data.job;
    if (!job || job.status !== "review") return;
    state.jobId = job.id;
    progress.classList.remove("hidden");
    showReview(job);
  })
  .catch(() => {});
