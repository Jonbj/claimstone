import { useEffect, useState } from "react";

// §4.2 rule 7: light and dark themes are both legible. §8.3: the dark theme is toggled
// with a `data-theme` attribute on <html>. The choice is per browser, and the default
// follows the OS preference.
type Theme = "light" | "dark";

function initialTheme(): Theme {
  const stored = localStorage.getItem("theme");
  if (stored === "dark" || stored === "light") return stored;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("theme", next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title="toggle light/dark theme"
      aria-label="toggle light/dark theme"
      className="cursor-pointer rounded-lg border border-gray-200 bg-white px-2 py-0.5 text-xs text-gray-700"
    >
      {theme === "dark" ? "light" : "dark"} theme
    </button>
  );
}
