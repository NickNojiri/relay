/**
 * Small date helpers so the prototype has no date-library dependency.
 *
 * IMPORTANT (production): everything here uses the *browser's* local time zone.
 * The Horn Center is always America/Los_Angeles, so a student booking from a
 * laptop set to another zone would see shifted hours. Before go-live, either pin
 * the zone with Intl.DateTimeFormat({ timeZone: "America/Los_Angeles" }) in the
 * formatters below, or do open-hours math server-side in a Power Automate flow.
 * Dataverse stores datetimes in UTC either way, which is what you want.
 */

export const MINUTE_MS = 60_000;

export function toDate(value: string | Date): Date {
  return value instanceof Date ? value : new Date(value);
}

export function minutesBetween(start: string | Date, end: string | Date): number {
  return (toDate(end).getTime() - toDate(start).getTime()) / MINUTE_MS;
}

export function addMinutes(value: string | Date, minutes: number): Date {
  return new Date(toDate(value).getTime() + minutes * MINUTE_MS);
}

export function startOfDay(value: string | Date): Date {
  const d = toDate(value);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function endOfDay(value: string | Date): Date {
  const d = startOfDay(value);
  d.setDate(d.getDate() + 1);
  return d;
}

/** Weeks start Sunday 00:00 local — matches how the weekly cap is described to students. */
export function startOfWeek(value: string | Date): Date {
  const d = startOfDay(value);
  d.setDate(d.getDate() - d.getDay());
  return d;
}

export function endOfWeek(value: string | Date): Date {
  const d = startOfWeek(value);
  d.setDate(d.getDate() + 7);
  return d;
}

export function sameDay(a: string | Date, b: string | Date): boolean {
  return startOfDay(a).getTime() === startOfDay(b).getTime();
}

/** Combine a calendar day with an "HH:MM" wall-clock string. */
export function atTime(day: string | Date, hhmm: string): Date {
  const [h, m] = hhmm.split(":").map(Number);
  const d = startOfDay(day);
  d.setHours(h, m, 0, 0);
  return d;
}

/** Half-open interval overlap: [aStart, aEnd) vs [bStart, bEnd). */
export function overlaps(
  aStart: string | Date,
  aEnd: string | Date,
  bStart: string | Date,
  bEnd: string | Date,
): boolean {
  return toDate(aStart) < toDate(bEnd) && toDate(bStart) < toDate(aEnd);
}

/** Minutes of [aStart, aEnd) that fall inside [bStart, bEnd). */
export function overlapMinutes(
  aStart: string | Date,
  aEnd: string | Date,
  bStart: string | Date,
  bEnd: string | Date,
): number {
  const start = Math.max(toDate(aStart).getTime(), toDate(bStart).getTime());
  const end = Math.min(toDate(aEnd).getTime(), toDate(bEnd).getTime());
  return end <= start ? 0 : (end - start) / MINUTE_MS;
}

export function formatTime(value: string | Date): string {
  return toDate(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/** "7a", "12p", "9p" — narrow enough to sit above a 30-minute grid column. */
export function formatHourShort(value: string | Date): string {
  const d = toDate(value);
  const hours = d.getHours();
  const hour12 = hours % 12 === 0 ? 12 : hours % 12;
  return `${hour12}${hours < 12 ? "a" : "p"}`;
}

export function formatDay(value: string | Date): string {
  return toDate(value).toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function formatRange(start: string | Date, end: string | Date): string {
  return `${formatTime(start)} – ${formatTime(end)}`;
}

export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

/** "2026-08-14" — for <input type="date"> round-tripping. */
export function toDateInputValue(value: string | Date): string {
  const d = toDate(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function fromDateInputValue(value: string): Date {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d);
}
