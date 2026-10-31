import vietnamese from "./locales/vi.json";

export type Locale = "en" | "vi";
const preferenceKey = "puppypi.locale";

function initialLocale(): Locale {
  try {
    return localStorage.getItem(preferenceKey) === "vi" ? "vi" : "en";
  } catch {
    return "en";
  }
}

let locale = initialLocale();
export const getLocale = (): Locale => locale;

export function setLocale(value: Locale): void {
  locale = value;
  document.documentElement.lang = value;
  try {
    localStorage.setItem(preferenceKey, value);
  } catch {
    // Language selection still works when browser storage is unavailable.
  }
}

export function t(message: string, values: Record<string, string | number> = {}): string {
  const translated =
    locale === "vi" ? ((vietnamese as Record<string, string>)[message] ?? message) : message;
  return translated.replace(/\{(\w+)\}/g, (placeholder, key: string) =>
    Object.hasOwn(values, key) ? String(values[key]) : placeholder,
  );
}
