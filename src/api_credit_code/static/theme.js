// Applies the saved light/dark choice before the page paints, so it doesn't flash the other theme.
try {
  const t = JSON.parse(localStorage.getItem("api-credit-code.prefs") || "{}").theme;
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch {
  // no saved choice: follow the system
}
