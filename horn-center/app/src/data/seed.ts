import type { Reservation, Resource, Student } from "../types";
import { addMinutes, atTime, startOfDay } from "../lib/time";

/**
 * Fixture data for the prototype.
 *
 * Resource names are placeholders — replace with the Horn Center's real inventory
 * before you demo to staff. Reservations are generated relative to "now" so the
 * kiosk view always has something in-progress to show.
 */

export const DEMO_STUDENT: Student = {
  id: "oid-00000000-0000-0000-0000-00000000dead",
  displayName: "Demo Student",
  email: "demo.student@student.csulb.edu",
  campusId: "012345678",
  roles: ["student"],
};

export const SEED_RESOURCES: Resource[] = [
  {
    id: "ws-01",
    name: "Workstation 1",
    kind: "workstation",
    location: "Horn Center — Main Lab",
    capacity: 1,
    features: ["dual-monitor", "Adobe CC"],
    isActive: true,
  },
  {
    id: "ws-02",
    name: "Workstation 2",
    kind: "workstation",
    location: "Horn Center — Main Lab",
    capacity: 1,
    features: ["dual-monitor", "Adobe CC"],
    isActive: true,
  },
  {
    id: "ws-03",
    name: "Workstation 3",
    kind: "workstation",
    location: "Horn Center — Main Lab",
    capacity: 1,
    features: ["SPSS", "MATLAB"],
    isActive: true,
  },
  {
    id: "ws-04",
    name: "Workstation 4",
    kind: "workstation",
    location: "Horn Center — Quiet Row",
    capacity: 1,
    features: ["standing desk"],
    isActive: true,
  },
  {
    id: "ws-05",
    name: "Workstation 5",
    kind: "workstation",
    location: "Horn Center — Quiet Row",
    capacity: 1,
    features: ["accessible desk"],
    isActive: true,
  },
  {
    id: "room-a",
    name: "Collab Room A",
    kind: "collab-room",
    location: "Horn Center — 2nd Floor",
    capacity: 6,
    features: ["whiteboard", "display", "video conferencing"],
    isActive: true,
  },
  {
    id: "room-b",
    name: "Collab Room B",
    kind: "collab-room",
    location: "Horn Center — 2nd Floor",
    capacity: 4,
    features: ["whiteboard"],
    isActive: true,
  },
  {
    id: "room-c",
    name: "Group Study C",
    kind: "collab-room",
    location: "Horn Center — 2nd Floor",
    capacity: 8,
    features: ["display", "moveable seating"],
    isActive: false,
  },
  {
    id: "kit-cam",
    name: "Camera Kit",
    kind: "equipment",
    location: "Horn Center — Front Desk",
    capacity: 1,
    features: ["DSLR", "tripod", "SD card"],
    isActive: true,
  },
  {
    id: "kit-vr",
    name: "VR Headset",
    kind: "equipment",
    location: "Horn Center — Front Desk",
    capacity: 1,
    features: ["Quest 3", "controllers"],
    isActive: true,
  },
];

const OTHER_STUDENTS = [
  { id: "oid-aaa", name: "A. Rivera" },
  { id: "oid-bbb", name: "J. Nguyen" },
  { id: "oid-ccc", name: "M. Okafor" },
  { id: "oid-ddd", name: "S. Patel" },
];

/** Reservations laid out around `now` so every view has something to render. */
export function seedReservations(now: Date): Reservation[] {
  const today = startOfDay(now);
  const rows: Reservation[] = [];
  let n = 0;
  const push = (row: Omit<Reservation, "id" | "createdAt">) => {
    rows.push({ ...row, id: `seed-${++n}`, createdAt: addMinutes(now, -240).toISOString() });
  };

  // In progress right now — drives the kiosk "in use" state.
  push({
    resourceId: "ws-01",
    studentId: OTHER_STUDENTS[0].id,
    studentName: OTHER_STUDENTS[0].name,
    startsAt: addMinutes(now, -30).toISOString(),
    endsAt: addMinutes(now, 60).toISOString(),
    status: "checked-in",
    checkedInAt: addMinutes(now, -28).toISOString(),
  });

  // Starting soon — drives "reserved soon".
  push({
    resourceId: "room-a",
    studentId: OTHER_STUDENTS[1].id,
    studentName: OTHER_STUDENTS[1].name,
    startsAt: addMinutes(now, 20).toISOString(),
    endsAt: addMinutes(now, 80).toISOString(),
    status: "booked",
  });

  // Scattered bookings later today so the grid is not empty.
  push({
    resourceId: "ws-03",
    studentId: OTHER_STUDENTS[2].id,
    studentName: OTHER_STUDENTS[2].name,
    startsAt: atTime(today, "14:00").toISOString(),
    endsAt: atTime(today, "15:30").toISOString(),
    status: "booked",
  });
  push({
    resourceId: "room-b",
    studentId: OTHER_STUDENTS[3].id,
    studentName: OTHER_STUDENTS[3].name,
    startsAt: atTime(today, "16:00").toISOString(),
    endsAt: atTime(today, "17:00").toISOString(),
    status: "booked",
  });
  push({
    resourceId: "kit-cam",
    studentId: OTHER_STUDENTS[0].id,
    studentName: OTHER_STUDENTS[0].name,
    startsAt: atTime(today, "11:00").toISOString(),
    endsAt: atTime(today, "12:00").toISOString(),
    status: "booked",
  });

  // One of the demo student's own bookings, tomorrow.
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  push({
    resourceId: "ws-02",
    studentId: DEMO_STUDENT.id,
    studentName: DEMO_STUDENT.displayName,
    startsAt: atTime(tomorrow, "10:00").toISOString(),
    endsAt: atTime(tomorrow, "11:30").toISOString(),
    status: "booked",
    purpose: "Senior project work",
  });

  // A completed session last week, so "past" has content.
  const lastWeek = new Date(today);
  lastWeek.setDate(lastWeek.getDate() - 6);
  push({
    resourceId: "room-a",
    studentId: DEMO_STUDENT.id,
    studentName: DEMO_STUDENT.displayName,
    startsAt: atTime(lastWeek, "13:00").toISOString(),
    endsAt: atTime(lastWeek, "14:00").toISOString(),
    status: "completed",
    checkedInAt: atTime(lastWeek, "13:02").toISOString(),
  });

  return rows;
}
