import type { Policy } from "../types";

/**
 * The Horn Center's booking rules, in one place.
 *
 * In production this lives in a Dataverse `hcr_policy` row (single active record)
 * so front-desk staff can change caps and hours without a redeploy — the shape is
 * identical, see docs/DATA-MODEL.md. Keep this object as the fallback/default.
 */
export const DEFAULT_POLICY: Policy = {
  slotMinutes: 30,
  minDurationMinutes: 30,
  maxDurationMinutes: 120,
  maxMinutesPerDay: 180,
  maxMinutesPerWeek: 600,
  maxActiveReservations: 3,
  advanceBookingDays: 7,
  checkInGraceMinutes: 15,
  openHours: {
    0: { open: "12:00", close: "18:00" }, // Sunday
    1: { open: "07:30", close: "22:00" },
    2: { open: "07:30", close: "22:00" },
    3: { open: "07:30", close: "22:00" },
    4: { open: "07:30", close: "22:00" },
    5: { open: "07:30", close: "18:00" },
    6: { open: "09:00", close: "17:00" }, // Saturday
  },
  blackouts: [],
};
