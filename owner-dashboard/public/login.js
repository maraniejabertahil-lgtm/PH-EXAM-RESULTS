const form = document.querySelector("#owner-login-form");
const emailInput = document.querySelector("#owner-email");
const passwordInput = document.querySelector("#owner-password");
const button = document.querySelector("#owner-login-button");
const message = document.querySelector("#login-message");

function showMessage(value, kind = "info") {
  message.textContent = value;
  message.dataset.kind = kind;
}
async function loadConfig() {
  const response = await fetch("/auth/firebase/config", { cache: "no-store" });
  const config = await response.json();
  if (!response.ok || !config.apiKey || !config.projectId) throw new Error(config.error || "Firebase sign-in is not configured.");
  return config;
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  button.disabled = true;
  showMessage("Checking your Firebase Owner account…");
  try {
    const config = await loadConfig();
    const authResponse = await fetch(
      "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=" + encodeURIComponent(config.apiKey),
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ email: emailInput.value.trim(), password: passwordInput.value, returnSecureToken: true }),
      },
    );
    const auth = await authResponse.json().catch(() => null);
    if (!authResponse.ok || !auth?.idToken) throw new Error("Firebase email or password is incorrect, or the account is unavailable.");
    const verifyResponse = await fetch("/auth/firebase", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ idToken: auth.idToken }),
    });
    const verification = await verifyResponse.json().catch(() => null);
    if (!verifyResponse.ok || verification?.authenticated !== true) {
      throw new Error(verification?.error || "Firebase Owner-role verification failed.");
    }
    passwordInput.value = "";
    showMessage("Firebase Owner verified. Continuing to the required GitHub identity check…", "success");
    location.assign("/auth/login");
  } catch (error) {
    showMessage(error instanceof Error ? error.message : "Owner sign-in failed.", "error");
    button.disabled = false;
  }
});
