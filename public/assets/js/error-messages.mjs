const SAFE_MESSAGES = Object.freeze({
  startup: "Published results could not be loaded. Check your connection and try again.",
  dataset: "The selected results could not be loaded or verified. Please try again.",
  search: "Search could not be completed. Reload the page and try again.",
  unexpected: "Something went wrong while using this page. Reload and try again.",
});

export function safeErrorMessage(context) {
  return SAFE_MESSAGES[context] || SAFE_MESSAGES.unexpected;
}

export function createDiagnosticReference(cryptoImpl = globalThis.crypto) {
  try {
    if (typeof cryptoImpl?.randomUUID === "function") {
      return cryptoImpl.randomUUID();
    }
  } catch {
    // Fall back to a short, local-only reference.
  }
  return Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}
