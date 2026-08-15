import type { BookingRequest, Policy, Reservation, Resource, Student } from "../types";
import { DEFAULT_POLICY } from "../lib/policy";
import { findNoShows, validateBooking } from "../lib/rules";
import { DEMO_STUDENT, SEED_RESOURCES, seedReservations } from "../data/seed";
import { overlaps, toDate } from "../lib/time";
import { BookingError, type ReservationService } from "./types";

const STORAGE_KEY = "horn-center.reservations.v1";

/**
 * localStorage-backed implementation — the demo backend.
 *
 * It re-validates on write (same rules module the UI uses) so the prototype
 * behaves like the real thing: you cannot get an illegal row in by racing the UI.
 */
export class MockReservationService implements ReservationService {
  private reservations: Reservation[];

  constructor(private readonly now: () => Date = () => new Date()) {
    this.reservations = this.load();
  }

  private load(): Reservation[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return JSON.parse(raw) as Reservation[];
    } catch {
      // Corrupt or unavailable storage — fall through to a fresh seed.
    }
    const seeded = seedReservations(this.now());
    this.persist(seeded);
    return seeded;
  }

  private persist(rows: Reservation[]): void {
    this.reservations = rows;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(rows));
    } catch {
      // Private browsing / quota — keep working in memory.
    }
  }

  /** Sweep expired holds the way the scheduled flow will in production. */
  private sweep(): Reservation[] {
    const now = this.now();
    const stale = new Set(findNoShows(this.reservations, now, DEFAULT_POLICY).map((r) => r.id));
    const completed = this.reservations.filter(
      (r) => r.status === "checked-in" && toDate(r.endsAt) <= now,
    );
    if (stale.size === 0 && completed.length === 0) return this.reservations;

    const completedIds = new Set(completed.map((r) => r.id));
    const next = this.reservations.map((r) =>
      stale.has(r.id)
        ? { ...r, status: "no-show" as const }
        : completedIds.has(r.id)
          ? { ...r, status: "completed" as const }
          : r,
    );
    this.persist(next);
    return next;
  }

  async getCurrentUser(): Promise<Student> {
    return DEMO_STUDENT;
  }

  async getPolicy(): Promise<Policy> {
    return DEFAULT_POLICY;
  }

  async listResources(): Promise<Resource[]> {
    return SEED_RESOURCES;
  }

  async listReservations(from: Date, to: Date): Promise<Reservation[]> {
    return this.sweep().filter((r) => overlaps(r.startsAt, r.endsAt, from, to));
  }

  async listMyReservations(studentId: string): Promise<Reservation[]> {
    return this.sweep().filter((r) => r.studentId === studentId);
  }

  async create(request: BookingRequest & { purpose?: string }): Promise<Reservation> {
    const rows = this.sweep();
    const resource = SEED_RESOURCES.find((r) => r.id === request.resourceId);
    const violations = validateBooking(request, {
      resource,
      existing: rows,
      policy: DEFAULT_POLICY,
      now: this.now(),
    });
    if (violations.length > 0) {
      throw new BookingError("That booking is not allowed.", violations);
    }

    const student = await this.getCurrentUser();
    const created: Reservation = {
      id: `res-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      resourceId: request.resourceId,
      studentId: request.studentId,
      studentName:
        request.studentId === student.id ? student.displayName : "Reserved",
      startsAt: request.startsAt,
      endsAt: request.endsAt,
      status: "booked",
      createdAt: this.now().toISOString(),
      purpose: request.purpose,
    };
    this.persist([...rows, created]);
    return created;
  }

  async cancel(reservationId: string): Promise<void> {
    this.persist(
      this.sweep().map((r) =>
        r.id === reservationId ? { ...r, status: "cancelled" as const } : r,
      ),
    );
  }

  async checkIn(reservationId: string): Promise<Reservation> {
    const now = this.now();
    let updated: Reservation | undefined;
    this.persist(
      this.sweep().map((r) => {
        if (r.id !== reservationId) return r;
        updated = { ...r, status: "checked-in" as const, checkedInAt: now.toISOString() };
        return updated;
      }),
    );
    if (!updated) throw new BookingError("Reservation not found.");
    return updated;
  }

  /** Demo affordance — wipes local state so a walkthrough can start clean. */
  reset(): void {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    this.reservations = this.load();
  }
}
