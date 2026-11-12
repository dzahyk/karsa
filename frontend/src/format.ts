const TZ = "Asia/Jakarta";

/** Whole-rupiah formatting with Indonesian-style grouping kept consistent: Rp150,000,000 (matches the spec). */
export function idr(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n < 0 ? "−" : "";
  return `${sign}Rp${Math.abs(Math.trunc(n)).toLocaleString("en-US")}`;
}

export function int(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-US");
}

export function pct(bp: number | null | undefined): string {
  if (bp === null || bp === undefined) return "—";
  const sign = bp < 0 ? "−" : "";
  const a = Math.abs(bp);
  return `${sign}${Math.floor(a / 100)}.${String(a % 100).padStart(2, "0")}%`;
}

export function valueDisplay(type: string, value: string | null): string {
  if (value === null || value === "") return "—";
  if (type === "idr") return idr(Number(value));
  if (type === "integer") return int(Number(value));
  if (type === "weeks") return `${value} week${value === "1" ? "" : "s"}`;
  if (type === "date") return dateOnly(`${value}T00:00:00Z`);
  return value;
}

/** Parse a user-typed rupiah/number field: digits only, separators allowed. Returns null when invalid. */
export function parseWhole(s: string): number | null {
  const cleaned = s.replace(/Rp|IDR|\s|[.,]/gi, "");
  if (!/^-?\d+$/.test(cleaned)) return null;
  const n = Number(cleaned);
  return Number.isSafeInteger(n) ? n : null;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ, day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(iso)) + " WIB";
}

export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));
}

export function relative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const diff = new Date(iso).getTime() - now;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 60_000) return "just now";
  if (abs < 3_600_000) return rtf.format(Math.round(diff / 60_000), "minute");
  if (abs < 86_400_000) return rtf.format(Math.round(diff / 3_600_000), "hour");
  return rtf.format(Math.round(diff / 86_400_000), "day");
}

export function shortHash(h: string | null | undefined): string {
  if (!h) return "—";
  return h.replace("sha256:", "").slice(0, 12);
}

export function pageOf(pageBreaks: number[], offset: number): number {
  return 1 + pageBreaks.filter((b) => b <= offset).length;
}
