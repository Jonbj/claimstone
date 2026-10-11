// Portal i18n (approved 2026-10-07): software labels only, local JSON catalogs, no runtime fetch.
// What a person types (project name, topics, terms, questions, rationales) and what the engine
// reports (claims, quotes) never passes through `t()`. A key that is missing shows itself: a
// visible bug is better than an invented label. Contract tokens (SUPPORTED, effect, …) stay
// canonical and are glossed beside, never replaced.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import en from "@/messages/en.json";
import it from "@/messages/it.json";

export const LOCALES = ["en", "it"] as const;
export type Locale = (typeof LOCALES)[number];
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", it: "Italiano" };
export type Messages = { [key: string]: string | Messages };
export type Params = Record<string, string | number>;

export const STORAGE_KEY = "claimstone-locale";

export function flatten(messages: Messages, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(messages)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out[path] = value;
    else Object.assign(out, flatten(value, path));
  }
  return out;
}

export const CATALOGS: Record<Locale, Record<string, string>> = {
  en: flatten(en as Messages),
  it: flatten(it as Messages),
};

export function translate(locale: Locale, key: string, params?: Params): string {
  const text = CATALOGS[locale][key];
  if (text === undefined) return key;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) =>
    params && name in params ? String(params[name]) : whole);
}

export function initialLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "it") return stored;
  } catch {
    // Storage can be blocked or absent; the page works without remembering.
  }
  const language = typeof navigator === "undefined" ? "" : String(navigator.language ?? "");
  return language.toLowerCase().startsWith("it") ? "it" : "en";
}

export interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, params?: Params) => string;
}

const FALLBACK: LocaleState = {
  locale: "en",
  setLocale: () => undefined,
  t: (key, params) => translate("en", key, params),
};

const LocaleContext = createContext<LocaleState>(FALLBACK);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not remembered; still switched.
    }
  }, []);

  const value = useMemo<LocaleState>(
    () => ({ locale, setLocale, t: (key, params) => translate(locale, key, params) }),
    [locale, setLocale],
  );
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleState {
  return useContext(LocaleContext);
}
