import type {
  BookingRequest,
  Policy,
  Reservation,
  Resource,
  Student,
} from "../types";

/**
 * The one seam between the UI and its backend.
 *
 * The prototype ships a localStorage implementation (mockService) and a Dataverse
 * implementation (dataverseService). Components only ever see this interface, so
 * flipping VITE_DATA_SOURCE is the entire migration.
 */
export interface ReservationService {
  /** The signed-in student. Mock returns a fixture; Dataverse reads the Entra token. */
  getCurrentUser(): Promise<Student>;
  getPolicy(): Promise<Policy>;
  listResources(): Promise<Resource[]>;
  /** All reservations overlapping [from, to) — every student's, for availability. */
  listReservations(from: Date, to: Date): Promise<Reservation[]>;
  /** Everything for one student, past and future. */
  listMyReservations(studentId: string): Promise<Reservation[]>;
  create(request: BookingRequest & { purpose?: string }): Promise<Reservation>;
  cancel(reservationId: string): Promise<void>;
  checkIn(reservationId: string): Promise<Reservation>;
}

export class BookingError extends Error {
  constructor(
    message: string,
    readonly violations: { code: string; message: string }[] = [],
  ) {
    super(message);
    this.name = "BookingError";
  }
}
