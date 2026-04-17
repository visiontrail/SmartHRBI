"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  DEFAULT_LOCALE,
  DICTIONARY,
  I18N_STORAGE_KEY,
  SUPPORTED_LOCALES,
  type DictionaryMap,
  type Locale,
} from "./dictionary";

type TranslateParams = Record<string, string | number | null | undefined>;

type I18nContextValue = {
  locale: Locale;
  setLocale: (nextLocale: Locale) => void;
  t: (key: string, params?: TranslateParams) => string;
};

function isLocale(value: string): value is Locale {
  return SUPPORTED_LOCALES.includes(value as Locale);
}

function interpolate(template: string, params?: TranslateParams): string {
  if (!params) {
    return template;
  }
  return template.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, token: string) => {
    const value = params[token];
    if (value === undefined || value === null) {
      return "";
    }
    return String(value);
  });
}

function translate(
  locale: Locale,
  key: string,
  params: TranslateParams | undefined,
  dictionary: Record<Locale, DictionaryMap>
): string {
  const localizedTemplate = dictionary[locale]?.[key];
  const fallbackTemplate = dictionary[DEFAULT_LOCALE]?.[key];
  const template = localizedTemplate ?? fallbackTemplate ?? key;
  return interpolate(template, params);
}

function resolveInitialLocale(): Locale {
  if (typeof window === "undefined") {
    return DEFAULT_LOCALE;
  }

  const storedLocale = window.localStorage.getItem(I18N_STORAGE_KEY);
  if (storedLocale && isLocale(storedLocale)) {
    return storedLocale;
  }

  const browserLocale = window.navigator.language;
  if (browserLocale.toLowerCase().startsWith("zh")) {
    return "zh-CN";
  }
  return DEFAULT_LOCALE;
}

const defaultContextValue: I18nContextValue = {
  locale: DEFAULT_LOCALE,
  setLocale: () => {
    // no-op fallback for tests or isolated rendering
  },
  t: (key: string, params?: TranslateParams) => translate(DEFAULT_LOCALE, key, params, DICTIONARY),
};

const I18nContext = createContext<I18nContextValue>(defaultContextValue);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  useEffect(() => {
    setLocaleState(resolveInitialLocale());
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(I18N_STORAGE_KEY, locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
  }, []);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key: string, params?: TranslateParams) => translate(locale, key, params, DICTIONARY),
    }),
    [locale, setLocale]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
