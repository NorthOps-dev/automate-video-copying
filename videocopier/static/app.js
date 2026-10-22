const form = document.getElementById("form");
const logEl = document.getElementById("log");
const progress = document.getElementById("progress");
const result = document.getElementById("result");
const missing = document.getElementById("missing");
const buildBtn = document.getElementById("build");
const drivePill = document.getElementById("drive-pill");

async function api(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Sign in required");
  }
  return res;
}

async function refreshDrive() {
  try {
    const h = await api("/api/health").then((r) => r.json());
    if (h.drive_connected) {
      drivePill.textContent = "Drive: connected";
      drivePill.classList.add("ok");
    } else if (h.google_drive_desktop?.length) {
      drivePill.textContent = "Drive Desktop folder found — paste a path or public link";
    } else if (h.drive_oauth_ready) {
      drivePill.textContent = "Drive: click Connect";
    } else {
      drivePill.textContent = "Drive: paste a public link, or a local folder";
    }
  } catch {
    drivePill.textContent = "Drive: offline";
  }
}

async function nativePick(url, extra = "") {
  const res = await api(url + extra, { method: "POST" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Picker failed");
  return data;
}

function setFootage(path, label) {
  document.getElementById("footage").value = path;
  const status = document.getElementById("footage-status");
  status.textContent = label;
  status.classList.remove("hidden");
}

document.getElementById("pick-folder").addEventListener("click", async () => {
  const btn = document.getElementById("pick-folder");
  btn.disabled = true;
  btn.textContent = "Waiting for Finder…";
  try {
    const data = await nativePick("/api/pick/folder");
    if (data.cancelled) return;
    setFootage(data.path, `${data.videos} video${data.videos === 1 ? "" : "s"} in ${data.path}`);
  } catch (err) {
    alert(err.message || err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Choose folder";
  }
});

document.getElementById("pick-footage-video").addEventListener("click", async () => {
  const btn = document.getElementById("pick-footage-video");
  btn.disabled = true;
  btn.textContent = "Waiting for Finder…";
  try {
    const data = await nativePick("/api/pick/file", "?kind=footage");
    if (data.cancelled) return;
    setFootage(data.path, `1 video: ${data.name}`);
  } catch (err) {
    alert(err.message || err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Choose video";
  }
});

document.getElementById("pick-ref").addEventListener("click", async () => {
  const btn = document.getElementById("pick-ref");
  btn.disabled = true;
  try {
    const data = await nativePick("/api/pick/file", "?kind=video");
    if (data.cancelled) return;
    document.getElementById("ref-url").value = data.path;
    document.getElementById("ref-file").value = "";
  } catch (err) {
    alert(err.message || err);
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("connect-drive").addEventListener("click", async () => {
  const base = window.location.origin;
  const res = await api(`/api/drive/connect?base=${encodeURIComponent(base)}`);
  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || "Add client_secret.json to connect a private Drive. Public links work without it.");
    return;
  }
  window.location = data.url;
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  result.classList.add("hidden");
  progress.classList.remove("hidden");
  logEl.innerHTML = "";
  buildBtn.disabled = true;

  const footage = document.getElementById("footage").value.trim();
  const refFile = document.getElementById("ref-file").files[0];
  const refUrl = document.getElementById("ref-url").value.trim();
  const captions = document.getElementById("captions").value;
  const music = document.getElementById("music").value.trim();

  let job;
  try {
    if (refFile) {
      const fd = new FormData();
      fd.append("reference_file", refFile);
      if (refUrl) fd.append("reference_url", refUrl);
      fd.append("footage", footage);
      fd.append("caption_mode", captions);
      if (music) fd.append("music", music);
      const res = await api("/api/jobs/upload", { method: "POST", body: fd });
      job = await res.json();
      if (!res.ok) throw new Error(job.detail || "Could not start job");
    } else {
      const res = await api("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reference: refUrl,
          footage,
          music: music || null,
          caption_mode: captions,
        }),
      });
      job = await res.json();
      if (!res.ok) throw new Error(job.detail || "Could not start job");
    }
  } catch (err) {
    addLog(String(err.message || err), true);
    buildBtn.disabled = false;
    return;
  }

  poll(job.id);
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
    const state = await api(`/api/jobs/${id}`).then((r) => r.json());
    for (const line of state.log || []) {
      if (!seen.has(line)) {
        seen.add(line);
        addLog(line, line.startsWith("Error"));
      }
    }
    if (state.status === "done") {
      buildBtn.disabled = false;
      showResult(id, state);
      return;
    }
    if (state.status === "error") {
      buildBtn.disabled = false;
      addLog(state.error || "Job failed", true);
      return;
    }
    setTimeout(tick, 1000);
  };
  tick();
}

function showResult(id, state) {
  result.classList.remove("hidden");
  const mp4 = `/api/jobs/${id}/file/mp4`;
  document.getElementById("player").src = mp4;
  document.getElementById("dl-mp4").href = mp4;
  document.getElementById("dl-xml").href = `/api/jobs/${id}/file/xml`;
  document.getElementById("dl-json").href = `/api/jobs/${id}/file/cutlist`;
  if (state.unfilled?.length) {
    missing.classList.remove("hidden");
    missing.querySelector("ul").innerHTML = state.unfilled
      .map((s) => `<li>${s}</li>`)
      .join("");
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

refreshDrive();
