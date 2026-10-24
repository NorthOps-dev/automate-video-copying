const form = document.getElementById("form");
const logEl = document.getElementById("log");
const progress = document.getElementById("progress");
const result = document.getElementById("result");
const missing = document.getElementById("missing");
const buildBtn = document.getElementById("build");
const boardPill = document.getElementById("board-pill");
const clipList = document.getElementById("clip-list");
const footageStatus = document.getElementById("footage-status");

const state = {
  clips: [],
  boardSlots: [],
  clients: [],
  boardId: "",
  clientId: "",
  brief: null,
  refMode: "board",
};

async function api(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Sign in required");
  }
  return res;
}

function setTab(paneId) {
  state.refMode = paneId === "pane-board" ? "board" : "file";
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("on", tab.dataset.pane === paneId);
  });
  document.getElementById("pane-board").classList.toggle("hidden", paneId !== "pane-board");
  document.getElementById("pane-file").classList.toggle("hidden", paneId !== "pane-file");
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => setTab(tab.dataset.pane));
});

async function nativePick(url, extra = "") {
  const res = await api(url + extra, { method: "POST" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Picker failed");
  return data;
}

function renderClips() {
  clipList.innerHTML = state.clips
    .map(
      (clip, i) =>
        `<li><span>${clip.name}</span><button type="button" data-i="${i}">Remove</button></li>`
    )
    .join("");
  footageStatus.classList.toggle("hidden", state.clips.length > 0);
  footageStatus.textContent = state.clips.length ? "" : "No clips yet.";
}

clipList.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-i]");
  if (!btn) return;
  state.clips.splice(Number(btn.dataset.i), 1);
  renderClips();
  persistClips();
});

function persistClips() {
  sessionStorage.setItem("prophetClips", JSON.stringify(state.clips));
}

function addClips(paths, names) {
  paths.forEach((path, i) => {
    if (state.clips.some((c) => c.path === path)) return;
    state.clips.push({ path, name: names[i] || path.split("/").pop() });
  });
  renderClips();
  persistClips();
}

document.getElementById("pick-folder").addEventListener("click", async () => {
  const btn = document.getElementById("pick-folder");
  btn.disabled = true;
  btn.textContent = "Waiting for Finder…";
  try {
    const data = await nativePick("/api/pick/folder");
    if (data.cancelled) return;
    addClips([data.path], [`${data.videos} videos in folder`]);
  } catch (err) {
    alert(err.message || err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Add a folder";
  }
});

document.getElementById("pick-footage-video").addEventListener("click", async () => {
  const btn = document.getElementById("pick-footage-video");
  btn.disabled = true;
  btn.textContent = "Waiting for Finder…";
  try {
    const data = await nativePick("/api/pick/files");
    if (data.cancelled) return;
    addClips(data.paths, data.names);
  } catch (err) {
    alert(err.message || err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Add videos";
  }
});

document.getElementById("pick-ref").addEventListener("click", async () => {
  const btn = document.getElementById("pick-ref");
  btn.disabled = true;
  try {
    const data = await nativePick("/api/pick/file", "?kind=video");
    if (data.cancelled) return;
    document.getElementById("ref-url").value = data.path;
    state.boardId = "";
    document.getElementById("format-preview").classList.remove("hidden");
    document.getElementById("format-hook").textContent = data.name || "Original";
    playOriginal(`/api/local/video?path=${encodeURIComponent(data.path)}`, "Play the original, then remake it.");
  } catch (err) {
    alert(err.message || err);
  } finally {
    btn.disabled = false;
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
  note.textContent = status || "Play the original, then remake it.";
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
  statusEl.textContent = `${rows.length} approved format${rows.length === 1 ? "" : "s"} for this client`;
  list.innerHTML = rows
    .slice(0, 80)
    .map((slot) => {
      const thumb = slot.thumb
        ? `<img src="/api/board/thumb?src=${encodeURIComponent(slot.thumb)}" alt="" />`
        : `<img alt="" />`;
      const script = slot.hasScript ? "Has remake script" : "Needs script";
      return `<button type="button" class="board-item ${slot.id === state.boardId ? "on" : ""}" data-id="${slot.id}">
        ${thumb}
        <span><strong>${slot.hook || "Untitled"}</strong><span class="meta">#${slot.slotNumber || "?"} · ${slot.status} · ${script}</span></span>
      </button>`;
    })
    .join("");
  if (!rows.length) {
    list.innerHTML = `<p class="hint">No approved formats for this client.</p>`;
  }
}

function esc(text) {
  return String(text).replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
}

function junkScript(text) {
  const t = String(text || "").replace(/\s+/g, " ").trim();
  return !t || t === "." || t.length < 12 || /^thank you\.?$/i.test(t);
}

async function showFormat(slotId) {
  const box = document.getElementById("format-preview");
  const hook = document.getElementById("format-hook");
  const lines = document.getElementById("format-lines");
  const slot = state.boardSlots.find((s) => s.id === slotId);
  hook.textContent = slot ? slot.hook : "";
  const preview = (slot?.scriptPreview || []).filter((t) => !junkScript(t));
  lines.innerHTML = preview.length
    ? preview.map((t) => `<li>${esc(t)}</li>`).join("")
    : "<li>Reading the words on the TikTok…</li>";
  box.classList.toggle("hidden", !slot);
  if (slotId) {
    playOriginal(`/api/board/slot/${slotId}/video`, "Play the original so you can remake the shots.");
  }
  try {
    const cards = await api(`/api/board/slot/${slotId}/cards`).then((r) => r.json());
    if (cards.ok && cards.cards?.length) {
      lines.innerHTML = cards.cards
        .slice(0, 8)
        .map((c) => `<li>${esc(c.text).replace(/\n/g, "<br>")}</li>`)
        .join("");
      box.classList.remove("hidden");
      return;
    }
  } catch {
    /* fall through to Board copy only if it is real sentences */
  }
  try {
    const data = await api(`/api/board/slot/${slotId}`).then((r) => r.json());
    if (!data.ok || !data.slot) return;
    const script = (data.slot.scriptLines || [])
      .map((item) => (item.brand || item.original || "").trim())
      .filter((t) => !junkScript(t));
    if (script.length) {
      lines.innerHTML = script.slice(0, 8).map((t) => `<li>${esc(t)}</li>`).join("");
    } else if (!preview.length) {
      lines.innerHTML = "<li>No on-screen words found yet — remake will read the video.</li>";
    }
    box.classList.remove("hidden");
  } catch {
    /* preview is optional */
  }
}

document.getElementById("board-list").addEventListener("click", (e) => {
  const item = e.target.closest(".board-item");
  if (!item) return;
  state.boardId = item.dataset.id;
  document.getElementById("ref-url").value = "";
  renderBoard();
  showFormat(state.boardId);
});

document.getElementById("board-search").addEventListener("input", renderBoard);

function briefPayload() {
  return {
    name: document.getElementById("client").selectedOptions[0]?.text || "",
    one_liner: document.getElementById("brief-one").value.trim(),
    location: document.getElementById("brief-loc").value.trim(),
    what: document.getElementById("brief-what").value.trim(),
    voice: document.getElementById("brief-voice").value.trim(),
    cta: document.getElementById("brief-cta").value.trim(),
    avoid: document.getElementById("brief-avoid").value.trim(),
  };
}

function fillBrief(brief) {
  state.brief = brief;
  document.getElementById("brief-one").value = brief.one_liner || "";
  document.getElementById("brief-loc").value = brief.location || "";
  document.getElementById("brief-what").value = brief.what || "";
  document.getElementById("brief-voice").value = brief.voice || "";
  document.getElementById("brief-cta").value = brief.cta || "";
  document.getElementById("brief-avoid").value = brief.avoid || "";
}

async function loadBrief(clientId, name) {
  const box = document.getElementById("brief-box");
  if (!clientId) {
    box.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");
  const brief = await api(`/api/briefs/${clientId}?name=${encodeURIComponent(name || "")}`).then((r) => r.json());
  fillBrief(brief);
}

document.getElementById("client").addEventListener("change", async (e) => {
  state.clientId = e.target.value;
  state.boardId = "";
  hidePreview();
  const name = e.target.selectedOptions[0]?.text || "";
  renderBoard();
  await loadBrief(state.clientId, name);
  buildBtn.textContent = state.clientId ? `Remake for ${name}` : "Remake for the client";
});

document.getElementById("save-brief").addEventListener("click", async () => {
  if (!state.clientId) return;
  const saved = document.getElementById("brief-saved");
  const btn = document.getElementById("save-brief");
  btn.disabled = true;
  try {
    const brief = await api(`/api/briefs/${state.clientId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(briefPayload()),
    }).then((r) => r.json());
    fillBrief(brief);
    saved.textContent = "Brief saved.";
    saved.classList.remove("hidden");
  } catch (err) {
    saved.textContent = err.message || "Could not save";
    saved.classList.remove("hidden");
  } finally {
    btn.disabled = false;
  }
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
      await loadBrief(melo.id, melo.name);
      buildBtn.textContent = `Remake for ${melo.name}`;
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
  progress.classList.remove("hidden");
  logEl.innerHTML = "";
  buildBtn.disabled = true;

  if (state.clientId) {
    try {
      await api(`/api/briefs/${state.clientId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(briefPayload()),
      });
    } catch {
      /* remake can still run on last saved brief */
    }
  }

  const captions = document.getElementById("captions").value;
  const music = document.getElementById("music").value.trim();
  const footagePaths = state.clips.map((c) => c.path);
  let reference = "";
  if (state.refMode === "board" && state.boardId) {
    reference = `board:${state.boardId}`;
  } else {
    reference = document.getElementById("ref-url").value.trim();
  }

  if (!state.clientId && state.refMode === "board") {
    addLog("Step 1 — pick the client.", true);
    buildBtn.disabled = false;
    return;
  }
  if (!reference) {
    addLog("Step 2 — pick the approved format to remake.", true);
    buildBtn.disabled = false;
    return;
  }
  if (!footagePaths.length) {
    addLog("Step 3 — add the client’s footage.", true);
    buildBtn.disabled = false;
    return;
  }

  try {
    const res = await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reference,
        footage: "",
        footage_paths: footagePaths,
        music: music || null,
        caption_mode: captions,
        client_id: state.clientId,
      }),
    });
    const job = await res.json();
    if (!res.ok) throw new Error(job.detail || "Could not start job");
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
    if (job.status === "done") {
      buildBtn.disabled = false;
      showResult(id, job);
      return;
    }
    if (job.status === "error") {
      buildBtn.disabled = false;
      addLog(job.error || "Job failed", true);
      return;
    }
    setTimeout(tick, 1000);
  };
  tick();
}

function showResult(id, job) {
  result.classList.remove("hidden");
  const mp4 = `/api/jobs/${id}/file/mp4?t=${Date.now()}`;
  document.getElementById("player").src = mp4;
  const compare = document.getElementById("compare-original");
  if (state.boardId) {
    compare.src = `/api/board/slot/${state.boardId}/video`;
  } else {
    const ref = document.getElementById("ref-url").value.trim();
    compare.src = ref && !/^https?:/i.test(ref) ? `/api/local/video?path=${encodeURIComponent(ref)}` : "";
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

async function loadLastRemake() {
  try {
    const data = await api("/api/jobs/latest").then((r) => r.json());
    if (!data.job) return;
    const spec = data.job.spec || {};
    if (!state.clips.length && spec.footage_paths?.length) {
      addClips(
        spec.footage_paths,
        spec.footage_paths.map((p) => p.split("/").pop())
      );
    }
    if ((spec.reference || "").startsWith("board:")) {
      state.boardId = spec.reference.split(":")[1];
      renderBoard();
      showFormat(state.boardId);
    }
    showResult(data.job.id, data.job);
    progress.classList.remove("hidden");
    logEl.innerHTML = "";
    for (const line of data.job.log || []) addLog(line, line.startsWith("Error"));
  } catch {
    /* first run has no remake yet */
  }
}

try {
  const saved = JSON.parse(sessionStorage.getItem("prophetClips") || "[]");
  if (Array.isArray(saved) && saved.length) {
    state.clips = saved.filter((c) => c && c.path);
  }
} catch {
  /* ignore */
}

loadBoard().then(loadLastRemake);
renderClips();
