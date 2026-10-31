import { t, getLocale } from "./i18n";
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch("/api" + path, {
    ...init,
    headers:
      init.body instanceof FormData
        ? init.headers
        : { "Content-Type": "application/json", ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      body.error?.message ||
        (typeof body.detail === "string"
          ? body.detail
          : t("Request failed ({status})", { status: response.status })),
    );
  }
  return response.json();
}
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const evidence = (sha: string) => "/api/evidence/" + encodeURIComponent(sha);
export const when = (date: string) =>
  new Date(date).toLocaleString(getLocale() === "vi" ? "vi-VN" : "en-GB", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
export const timeOf = (date: string) =>
  new Date(date).toLocaleTimeString(getLocale() === "vi" ? "vi-VN" : "en-GB", { hour12: false });
