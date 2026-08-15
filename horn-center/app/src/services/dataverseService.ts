import type {
  BookingRequest,
  Policy,
  Reservation,
  ReservationStatus,
  Resource,
  ResourceKind,
  Student,
} from "../types";
import { DEFAULT_POLICY } from "../lib/policy";
import { BookingError, type ReservationService } from "./types";

/**
 * Production adapter: Dataverse Web API.
 *
 * Table/column names use the `hcr` publisher prefix created by
 * scripts/provision-dataverse.mjs — if you change the prefix there, change the
 * constants here. See docs/DATA-MODEL.md for the full schema.
 *
 * Two ways to get a token into `getToken`:
 *   1. Power Apps Code App — the Power SDK gives you an authenticated client and
 *      you can drop this file entirely in favour of the generated services.
 *   2. Standalone SPA (Static Web App / campus hosting) — MSAL browser, scope
 *      `https://<org>.crm.dynamics.com/user_impersonation`. Snippet in docs/SETUP.md.
 *
 * NOTE: this adapter is written against the documented Web API shapes but has not
 * been run against a live org — expect to correct one or two logical names the
 * first time you point it at Dataverse.
 */

const STATUS_TO_CHOICE: Record<ReservationStatus, number> = {
  booked: 1,
  "checked-in": 2,
  completed: 3,
  cancelled: 4,
  "no-show": 5,
};

const CHOICE_TO_STATUS: Record<number, ReservationStatus> = Object.fromEntries(
  Object.entries(STATUS_TO_CHOICE).map(([k, v]) => [v, k as ReservationStatus]),
) as Record<number, ReservationStatus>;

const KIND_TO_CHOICE: Record<ResourceKind, number> = {
  workstation: 1,
  "collab-room": 2,
  equipment: 3,
};

const CHOICE_TO_KIND: Record<number, ResourceKind> = Object.fromEntries(
  Object.entries(KIND_TO_CHOICE).map(([k, v]) => [v, k as ResourceKind]),
) as Record<number, ResourceKind>;

export interface DataverseConfig {
  /** e.g. https://org12345.crm.dynamics.com */
  orgUrl: string;
  /** Returns a bearer token scoped to `${orgUrl}/.default`. */
  getToken: () => Promise<string>;
  /** Signed-in user, from the id token claims. */
  getUser: () => Promise<Student>;
  apiVersion?: string;
}

interface ResourceRow {
  hcr_resourceid: string;
  hcr_name: string;
  hcr_kind: number;
  hcr_location: string | null;
  hcr_capacity: number | null;
  hcr_features: string | null;
  statecode: number;
}

interface ReservationRow {
  hcr_reservationid: string;
  _hcr_resource_value: string;
  hcr_studentaadid: string;
  hcr_studentname: string | null;
  hcr_startsat: string;
  hcr_endsat: string;
  hcr_status: number;
  hcr_checkedinat: string | null;
  hcr_purpose: string | null;
  createdon: string;
}

interface PolicyRow {
  hcr_slotminutes: number | null;
  hcr_minduration: number | null;
  hcr_maxduration: number | null;
  hcr_maxminutesperday: number | null;
  hcr_maxminutesperweek: number | null;
  hcr_maxactive: number | null;
  hcr_advancedays: number | null;
  hcr_checkingrace: number | null;
  /** JSON blob: { "1": { "open": "07:30", "close": "22:00" }, ... }. */
  hcr_openhoursjson: string | null;
  /** JSON blob: [{ start, end, reason }]. */
  hcr_blackoutsjson: string | null;
}

export class DataverseReservationService implements ReservationService {
  private readonly base: string;

  constructor(private readonly config: DataverseConfig) {
    this.base = `${config.orgUrl.replace(/\/$/, "")}/api/data/${config.apiVersion ?? "v9.2"}`;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = await this.config.getToken();
    const response = await fetch(`${this.base}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        // Return the created/updated row instead of a bare 204.
        Prefer: "return=representation",
        ...init.headers,
      },
    });

    if (!response.ok) {
      const body = await response.text();
      // Dataverse surfaces plug-in errors here — that is where the server-side
      // copy of the booking rules reports a conflict.
      throw new BookingError(parseDataverseError(body, response.status));
    }

    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  async getCurrentUser(): Promise<Student> {
    return this.config.getUser();
  }

  async getPolicy(): Promise<Policy> {
    const result = await this.request<{ value: PolicyRow[] }>(
      "/hcr_policies?$filter=statecode eq 0&$top=1",
    );
    const row = result.value[0];
    if (!row) return DEFAULT_POLICY;
    return {
      slotMinutes: row.hcr_slotminutes ?? DEFAULT_POLICY.slotMinutes,
      minDurationMinutes: row.hcr_minduration ?? DEFAULT_POLICY.minDurationMinutes,
      maxDurationMinutes: row.hcr_maxduration ?? DEFAULT_POLICY.maxDurationMinutes,
      maxMinutesPerDay: row.hcr_maxminutesperday ?? DEFAULT_POLICY.maxMinutesPerDay,
      maxMinutesPerWeek: row.hcr_maxminutesperweek ?? DEFAULT_POLICY.maxMinutesPerWeek,
      maxActiveReservations: row.hcr_maxactive ?? DEFAULT_POLICY.maxActiveReservations,
      advanceBookingDays: row.hcr_advancedays ?? DEFAULT_POLICY.advanceBookingDays,
      checkInGraceMinutes: row.hcr_checkingrace ?? DEFAULT_POLICY.checkInGraceMinutes,
      openHours: parseJson(row.hcr_openhoursjson, DEFAULT_POLICY.openHours),
      blackouts: parseJson(row.hcr_blackoutsjson, DEFAULT_POLICY.blackouts),
    };
  }

  async listResources(): Promise<Resource[]> {
    const select =
      "$select=hcr_resourceid,hcr_name,hcr_kind,hcr_location,hcr_capacity,hcr_features,statecode";
    const result = await this.request<{ value: ResourceRow[] }>(
      `/hcr_resources?${select}&$orderby=hcr_name asc`,
    );
    return result.value.map(toResource);
  }

  async listReservations(from: Date, to: Date): Promise<Reservation[]> {
    // Half-open overlap in OData: starts before the window ends AND ends after it starts.
    const filter = [
      `hcr_startsat lt ${to.toISOString()}`,
      `hcr_endsat gt ${from.toISOString()}`,
      // Cancelled and no-show rows do not hold a slot; leave them out of availability.
      `(hcr_status eq ${STATUS_TO_CHOICE.booked} or hcr_status eq ${STATUS_TO_CHOICE["checked-in"]} or hcr_status eq ${STATUS_TO_CHOICE.completed})`,
    ].join(" and ");

    const result = await this.request<{ value: ReservationRow[] }>(
      `/hcr_reservations?$select=${RESERVATION_SELECT}&$filter=${encodeURIComponent(filter)}`,
    );
    return result.value.map(toReservation);
  }

  async listMyReservations(studentId: string): Promise<Reservation[]> {
    const filter = `hcr_studentaadid eq '${escapeODataString(studentId)}'`;
    const result = await this.request<{ value: ReservationRow[] }>(
      `/hcr_reservations?$select=${RESERVATION_SELECT}&$filter=${encodeURIComponent(
        filter,
      )}&$orderby=hcr_startsat desc`,
    );
    return result.value.map(toReservation);
  }

  async create(request: BookingRequest & { purpose?: string }): Promise<Reservation> {
    const user = await this.getCurrentUser();
    const payload = {
      "hcr_Resource@odata.bind": `/hcr_resources(${request.resourceId})`,
      hcr_studentaadid: request.studentId,
      hcr_studentname: user.displayName,
      hcr_startsat: request.startsAt,
      hcr_endsat: request.endsAt,
      hcr_status: STATUS_TO_CHOICE.booked,
      hcr_purpose: request.purpose ?? null,
      // Primary name column — makes rows readable in the model-driven admin app.
      hcr_name: `${user.displayName} · ${new Date(request.startsAt).toLocaleString()}`,
    };
    const row = await this.request<ReservationRow>("/hcr_reservations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return toReservation(row);
  }

  async cancel(reservationId: string): Promise<void> {
    await this.request<void>(`/hcr_reservations(${reservationId})`, {
      method: "PATCH",
      body: JSON.stringify({ hcr_status: STATUS_TO_CHOICE.cancelled }),
      headers: { Prefer: "return=minimal" },
    });
  }

  async checkIn(reservationId: string): Promise<Reservation> {
    const row = await this.request<ReservationRow>(`/hcr_reservations(${reservationId})`, {
      method: "PATCH",
      body: JSON.stringify({
        hcr_status: STATUS_TO_CHOICE["checked-in"],
        hcr_checkedinat: new Date().toISOString(),
      }),
    });
    return toReservation(row);
  }
}

const RESERVATION_SELECT =
  "hcr_reservationid,_hcr_resource_value,hcr_studentaadid,hcr_studentname,hcr_startsat,hcr_endsat,hcr_status,hcr_checkedinat,hcr_purpose,createdon";

function toResource(row: ResourceRow): Resource {
  return {
    id: row.hcr_resourceid,
    name: row.hcr_name,
    kind: CHOICE_TO_KIND[row.hcr_kind] ?? "workstation",
    location: row.hcr_location ?? "",
    capacity: row.hcr_capacity ?? 1,
    features: (row.hcr_features ?? "")
      .split(";")
      .map((f) => f.trim())
      .filter(Boolean),
    isActive: row.statecode === 0,
  };
}

function toReservation(row: ReservationRow): Reservation {
  return {
    id: row.hcr_reservationid,
    resourceId: row._hcr_resource_value,
    studentId: row.hcr_studentaadid,
    studentName: row.hcr_studentname ?? "Reserved",
    startsAt: row.hcr_startsat,
    endsAt: row.hcr_endsat,
    status: CHOICE_TO_STATUS[row.hcr_status] ?? "booked",
    createdAt: row.createdon,
    checkedInAt: row.hcr_checkedinat ?? undefined,
    purpose: row.hcr_purpose ?? undefined,
  };
}

function parseJson<T>(raw: string | null, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/** OData string literals escape a single quote by doubling it. */
function escapeODataString(value: string): string {
  return value.replace(/'/g, "''");
}

function parseDataverseError(body: string, status: number): string {
  try {
    const parsed = JSON.parse(body) as { error?: { message?: string } };
    if (parsed.error?.message) return parsed.error.message;
  } catch {
    // fall through
  }
  return `Dataverse request failed (${status}).`;
}
