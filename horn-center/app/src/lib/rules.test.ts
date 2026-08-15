import { describe, expect, it } from "vitest";
import { DEFAULT_POLICY } from "./policy";
import {
  buildDaySlots,
  findNoShows,
  nextBookableDay,
  resourceStateAt,
  usageSummary,
  validateBooking,
} from "./rules";
import type { Policy, Reservation, Resource, ViolationCode } from "../types";

// Wednesday 16 Sep 2026 — open 07:30–22:00 under DEFAULT_POLICY.
// The week containing it runs Sun 13 Sep → Sun 20 Sep.
const NOW = new Date(2026, 8, 16, 9, 0, 0);

const STATION: Resource = {
  id: "res-1",
  name: "Workstation 12",
  kind: "workstation",
  location: "Horn Center — Main Lab",
  capacity: 1,
  features: ["dual-monitor"],
  isActive: true,
};

const policy: Policy = DEFAULT_POLICY;

function at(hour: number, minute = 0, day = 16): string {
  return new Date(2026, 8, day, hour, minute, 0).toISOString();
}

function reservation(over: Partial<Reservation> = {}): Reservation {
  return {
    id: "r-1",
    resourceId: STATION.id,
    studentId: "stu-1",
    studentName: "Test Student",
    startsAt: at(10),
    endsAt: at(11),
    status: "booked",
    createdAt: at(8),
    ...over,
  };
}

function codes(violations: { code: ViolationCode }[]): ViolationCode[] {
  return violations.map((v) => v.code);
}

function validate(over: Partial<Parameters<typeof validateBooking>[0]> = {}, existing: Reservation[] = []) {
  return validateBooking(
    {
      resourceId: STATION.id,
      studentId: "stu-1",
      startsAt: at(13),
      endsAt: at(14),
      ...over,
    },
    { resource: STATION, existing, policy, now: NOW },
  );
}

describe("validateBooking", () => {
  it("accepts a well-formed booking inside open hours", () => {
    expect(validate()).toEqual([]);
  });

  it("rejects times in the past", () => {
    expect(codes(validate({ startsAt: at(7, 30), endsAt: at(8, 0) }))).toContain(
      "IN_THE_PAST",
    );
  });

  it("rejects bookings outside open hours", () => {
    // Center closes at 22:00 on a Wednesday.
    expect(codes(validate({ startsAt: at(21, 30), endsAt: at(22, 30) }))).toContain(
      "OUTSIDE_OPEN_HOURS",
    );
  });

  it("rejects starts that are off the 30-minute grid", () => {
    expect(codes(validate({ startsAt: at(13, 10), endsAt: at(13, 40) }))).toContain(
      "NOT_ON_SLOT_GRID",
    );
  });

  it("rejects bookings longer than the per-booking maximum", () => {
    expect(codes(validate({ startsAt: at(13), endsAt: at(16) }))).toContain("TOO_LONG");
  });

  it("rejects bookings shorter than one slot", () => {
    const short = validateBooking(
      {
        resourceId: STATION.id,
        studentId: "stu-1",
        startsAt: at(13),
        endsAt: at(13, 15),
      },
      { resource: STATION, existing: [], policy, now: NOW },
    );
    expect(codes(short)).toContain("TOO_SHORT");
  });

  it("rejects bookings past the advance-booking horizon", () => {
    const beyond = new Date(2026, 8, 16 + policy.advanceBookingDays + 1, 13, 0).toISOString();
    const beyondEnd = new Date(2026, 8, 16 + policy.advanceBookingDays + 1, 14, 0).toISOString();
    expect(codes(validate({ startsAt: beyond, endsAt: beyondEnd }))).toContain(
      "BEYOND_BOOKING_HORIZON",
    );
  });

  it("rejects an inactive resource", () => {
    const result = validateBooking(
      { resourceId: STATION.id, studentId: "stu-1", startsAt: at(13), endsAt: at(14) },
      { resource: { ...STATION, isActive: false }, existing: [], policy, now: NOW },
    );
    expect(codes(result)).toContain("RESOURCE_INACTIVE");
  });

  it("rejects an overlap on the same resource by another student", () => {
    const existing = [reservation({ studentId: "stu-2", startsAt: at(13), endsAt: at(14) })];
    expect(codes(validate({}, existing))).toContain("RESOURCE_DOUBLE_BOOKED");
  });

  it("allows booking a slot freed by a cancellation", () => {
    const existing = [
      reservation({ studentId: "stu-2", startsAt: at(13), endsAt: at(14), status: "cancelled" }),
    ];
    expect(validate({}, existing)).toEqual([]);
  });

  it("allows booking a slot freed by a no-show", () => {
    const existing = [
      reservation({ studentId: "stu-2", startsAt: at(13), endsAt: at(14), status: "no-show" }),
    ];
    expect(validate({}, existing)).toEqual([]);
  });

  it("rejects a student double-booking themselves on a different resource", () => {
    const existing = [
      reservation({ resourceId: "res-2", startsAt: at(13), endsAt: at(14) }),
    ];
    expect(codes(validate({}, existing))).toContain("STUDENT_DOUBLE_BOOKED");
  });

  it("enforces the daily cap", () => {
    // 180 min/day cap: two 90-minute sessions already booked leaves nothing.
    const existing = [
      reservation({ id: "a", startsAt: at(10), endsAt: at(11, 30), resourceId: "res-9" }),
      reservation({ id: "b", startsAt: at(11, 30), endsAt: at(13), resourceId: "res-9" }),
    ];
    expect(codes(validate({ startsAt: at(15), endsAt: at(16) }, existing))).toContain(
      "DAILY_CAP_EXCEEDED",
    );
  });

  it("does not count another day's usage against today's cap", () => {
    const existing = [
      reservation({ id: "a", startsAt: at(10, 0, 17), endsAt: at(12, 0, 17), resourceId: "res-9" }),
    ];
    expect(codes(validate({ startsAt: at(15), endsAt: at(16) }, existing))).not.toContain(
      "DAILY_CAP_EXCEEDED",
    );
  });

  it("enforces the weekly cap across days in the same week", () => {
    // 600 min/week. Book 2h on Mon, Tue, Wed, Thu, Fri = 600, so one more fails.
    const existing = [14, 15, 16, 17, 18].map((day, i) =>
      reservation({
        id: `w-${i}`,
        resourceId: `res-${i}`,
        startsAt: at(8, 0, day),
        endsAt: at(10, 0, day),
      }),
    );
    expect(codes(validate({ startsAt: at(15), endsAt: at(16) }, existing))).toContain(
      "WEEKLY_CAP_EXCEEDED",
    );
  });

  it("enforces the concurrent-reservation cap", () => {
    const existing = [1, 2, 3].map((n) =>
      reservation({
        id: `u-${n}`,
        resourceId: `res-${n}`,
        startsAt: at(9, 0, 16 + n),
        endsAt: at(9, 30, 16 + n),
      }),
    );
    expect(codes(validate({}, existing))).toContain("TOO_MANY_ACTIVE");
  });

  it("rejects a booking inside a blackout window", () => {
    const withBlackout: Policy = {
      ...policy,
      blackouts: [{ start: at(12), end: at(18), reason: "Lab maintenance" }],
    };
    const result = validateBooking(
      { resourceId: STATION.id, studentId: "stu-1", startsAt: at(13), endsAt: at(14) },
      { resource: STATION, existing: [], policy: withBlackout, now: NOW },
    );
    expect(codes(result)).toContain("BLACKOUT");
  });

  it("ignores the reservation being edited", () => {
    const existing = [reservation({ id: "editing", startsAt: at(13), endsAt: at(14) })];
    const result = validateBooking(
      { resourceId: STATION.id, studentId: "stu-1", startsAt: at(13), endsAt: at(14) },
      { resource: STATION, existing, policy, now: NOW, ignoreReservationId: "editing" },
    );
    expect(result).toEqual([]);
  });

  it("reports every violation at once, not just the first", () => {
    const result = validate({ startsAt: at(6, 10), endsAt: at(6, 20) });
    expect(result.length).toBeGreaterThan(2);
  });
});

describe("buildDaySlots", () => {
  it("covers the full open window on the 30-minute grid", () => {
    const slots = buildDaySlots({
      resource: STATION,
      day: NOW,
      reservations: [],
      policy,
      now: NOW,
    });
    // 07:30 → 22:00 is 14.5 hours = 29 slots of 30 minutes.
    expect(slots).toHaveLength(29);
    expect(new Date(slots[0].startsAt).getHours()).toBe(7);
    expect(new Date(slots[slots.length - 1].endsAt).getHours()).toBe(22);
  });

  it("returns nothing on a closed day", () => {
    const closed: Policy = { ...policy, openHours: { ...policy.openHours, 3: null } };
    expect(
      buildDaySlots({ resource: STATION, day: NOW, reservations: [], policy: closed, now: NOW }),
    ).toEqual([]);
  });

  it("marks booked slots taken and elapsed slots past", () => {
    const slots = buildDaySlots({
      resource: STATION,
      day: NOW,
      reservations: [reservation({ startsAt: at(13), endsAt: at(14) })],
      policy,
      now: NOW,
    });
    const taken = slots.filter((s) => s.status === "taken");
    expect(taken).toHaveLength(2);
    expect(slots.filter((s) => s.status === "past").length).toBeGreaterThan(0);
  });

  it("blocks slots the given student cannot take, with a reason", () => {
    const existing = [
      reservation({ id: "a", resourceId: "res-9", startsAt: at(10), endsAt: at(11, 30) }),
      reservation({ id: "b", resourceId: "res-9", startsAt: at(11, 30), endsAt: at(13) }),
    ];
    const slots = buildDaySlots({
      resource: STATION,
      day: NOW,
      reservations: existing,
      policy,
      now: NOW,
      studentId: "stu-1",
    });
    const blocked = slots.filter((s) => s.status === "blocked");
    expect(blocked.length).toBeGreaterThan(0);
    expect(blocked[0].reason).toMatch(/Daily limit/);
  });
});

describe("resourceStateAt", () => {
  it("reports in-use during a booking", () => {
    const state = resourceStateAt({
      resource: STATION,
      reservations: [reservation({ startsAt: at(8, 30), endsAt: at(10) })],
      policy,
      now: NOW,
    });
    expect(state.kind).toBe("in-use");
  });

  it("reports reserved-soon inside the lookahead", () => {
    const state = resourceStateAt({
      resource: STATION,
      reservations: [reservation({ startsAt: at(9, 30), endsAt: at(10) })],
      policy,
      now: NOW,
    });
    expect(state.kind).toBe("reserved-soon");
  });

  it("reports available when the next booking is far off", () => {
    const state = resourceStateAt({
      resource: STATION,
      reservations: [reservation({ startsAt: at(15), endsAt: at(16) })],
      policy,
      now: NOW,
    });
    expect(state.kind).toBe("available");
  });

  it("reports closed outside open hours", () => {
    const state = resourceStateAt({
      resource: STATION,
      reservations: [],
      policy,
      now: new Date(2026, 8, 16, 6, 0),
    });
    expect(state.kind).toBe("closed");
  });
});

describe("findNoShows", () => {
  it("flags un-checked-in bookings past the grace period", () => {
    const late = reservation({ startsAt: at(8, 30), endsAt: at(10) });
    expect(findNoShows([late], NOW, policy).map((r) => r.id)).toEqual(["r-1"]);
  });

  it("leaves checked-in bookings alone", () => {
    const checkedIn = reservation({
      startsAt: at(8, 30),
      endsAt: at(10),
      status: "checked-in",
      checkedInAt: at(8, 35),
    });
    expect(findNoShows([checkedIn], NOW, policy)).toEqual([]);
  });

  it("leaves bookings inside the grace period alone", () => {
    const justStarted = reservation({ startsAt: at(8, 50), endsAt: at(10) });
    expect(findNoShows([justStarted], NOW, policy)).toEqual([]);
  });
});

describe("nextBookableDay", () => {
  it("stays on today while the center is still open", () => {
    expect(nextBookableDay(NOW, policy).getDate()).toBe(16);
  });

  it("rolls to tomorrow once today has closed", () => {
    // Wednesday 22:30, after the 22:00 close.
    const afterHours = new Date(2026, 8, 16, 22, 30);
    expect(nextBookableDay(afterHours, policy).getDate()).toBe(17);
  });

  it("skips days the center is closed", () => {
    const closedThursday: Policy = {
      ...policy,
      openHours: { ...policy.openHours, 4: null },
    };
    const afterHours = new Date(2026, 8, 16, 22, 30);
    expect(nextBookableDay(afterHours, closedThursday).getDate()).toBe(18);
  });

  it("falls back to today when nothing in the horizon is open", () => {
    const neverOpen: Policy = {
      ...policy,
      openHours: { 0: null, 1: null, 2: null, 3: null, 4: null, 5: null, 6: null },
    };
    expect(nextBookableDay(NOW, neverOpen).getDate()).toBe(16);
  });
});

describe("usageSummary", () => {
  it("totals a student's day and week", () => {
    const existing = [
      reservation({ id: "a", startsAt: at(10), endsAt: at(11) }),
      reservation({ id: "b", resourceId: "res-2", startsAt: at(10, 0, 15), endsAt: at(12, 0, 15) }),
      reservation({ id: "other", studentId: "stu-2", startsAt: at(14), endsAt: at(15) }),
    ];
    const summary = usageSummary(existing, "stu-1", NOW, policy);
    expect(summary.dayUsed).toBe(60);
    expect(summary.weekUsed).toBe(180);
    expect(summary.dayLeft).toBe(120);
    expect(summary.weekLeft).toBe(420);
  });
});
