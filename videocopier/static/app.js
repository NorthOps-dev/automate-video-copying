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

const state = {
  clips: [],
  boardSlots: [],
  clients: [],
  boardId: "",
  clientId: "",
  jobId: "",
  draft: [],
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
  renderCaptionRows();
  review.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderCaptionRows() {
  captionEditor.innerHTML = state.draft
    .map((c, i) => {
      const face = c.face === "box" ? "box" : "classic";
      return `<div class="caption-row" data-i="${i}">
        <div class="times">
          <label>In<input type="number" step="0.1" min="0" class="t-start" value="${fmtTime(c.start)}"></label>
          <label>Out<input type="number" step="0.1" min="0" class="t-end" value="${fmtTime(c.end)}"></label>
        </div>
        <textarea class="t-text" rows="3">${esc(c.text)}</textarea>
        <div class="side">
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

function syncDraftFromDom() {
  [...captionEditor.querySelectorAll(".caption-row")].forEach((row) => {
    const i = Number(row.dataset.i);
    const card = state.draft[i];
    if (!card) return;
    const start = Number(row.querySelector(".t-start").value);
    const end = Number(row.querySelector(".t-end").value);
    card.start = Number.isFinite(start) ? start : 0;
    card.end = Number.isFinite(end) ? end : card.start + 1;
    card.text = row.querySelector(".t-text").value;
    card.face = row.querySelector(".t-face").value;
    card.kind = "overlay";
  });
}

captionEditor.addEventListener("click", (e) => {
  const btn = e.target.closest(".remove");
  if (!btn) return;
  syncDraftFromDom();
  const row = btn.closest(".caption-row");
  state.draft.splice(Number(row.dataset.i), 1);
  renderCaptionRows();
});

document.getElementById("add-card").addEventListener("click", () => {
  syncDraftFromDom();
  const last = state.draft[state.draft.length - 1];
  const start = last ? Number(last.end) || 0 : 0;
  state.draft.push({
    text: "",
    start,
    end: start + 2,
    face: last?.face || "classic",
    y_ratio: last?.y_ratio ?? 0.22,
    width_ratio: last?.width_ratio ?? 0,
    size_ratio: last?.size_ratio ?? 0,
    kind: "overlay",
  });
  renderCaptionRows();
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
