<script>
  // §4.2 rule 7: light and dark themes are both legible. The choice is per browser,
  // and the default follows the OS preference.
  const stored = typeof localStorage !== "undefined" ? localStorage.getItem("theme") : null;
  let theme = $state(
    stored === "dark" || stored === "light"
      ? stored
      : typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light",
  );

  $effect(() => {
    document.documentElement.dataset.theme = theme;
    if (stored !== null || theme !== "light") localStorage.setItem("theme", theme);
  });

  function toggle() {
    theme = theme === "dark" ? "light" : "dark";
    localStorage.setItem("theme", theme);
  }
</script>

<button onclick={toggle} title="toggle light/dark theme" aria-label="toggle light/dark theme">
  {theme === "dark" ? "light" : "dark"} theme
</button>

<style>
  button {
    background: none;
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    color: var(--fg);
    font-size: 0.75rem;
    padding: 0.1rem 0.5rem;
    cursor: pointer;
  }
</style>