const form = document.getElementById("login-form");
const errorEl = document.getElementById("login-error");
const btn = document.getElementById("signin");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorEl.classList.add("hidden");
  btn.disabled = true;
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: document.getElementById("email").value.trim(),
        password: document.getElementById("password").value,
      }),
    });
    if (!res.ok) {
      errorEl.classList.remove("hidden");
      return;
    }
    window.location.href = "/";
  } catch {
    errorEl.textContent = "Could not reach Prophet. Is the server running?";
    errorEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
  }
});
