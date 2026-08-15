import { MockReservationService } from "./mockService";
import { DataverseReservationService } from "./dataverseService";
import type { ReservationService } from "./types";

export * from "./types";
export { MockReservationService } from "./mockService";
export { DataverseReservationService } from "./dataverseService";

/**
 * Pick the backend from the environment.
 *
 * VITE_DATA_SOURCE=mock       (default) localStorage, no sign-in, runs anywhere.
 * VITE_DATA_SOURCE=dataverse  live org — also needs VITE_DATAVERSE_URL and a token
 *                             provider wired in below (MSAL or the Power SDK).
 */
export function createService(): ReservationService {
  const source = import.meta.env.VITE_DATA_SOURCE ?? "mock";

  if (source === "dataverse") {
    const orgUrl = import.meta.env.VITE_DATAVERSE_URL;
    if (!orgUrl) {
      throw new Error("VITE_DATAVERSE_URL must be set when VITE_DATA_SOURCE=dataverse");
    }
    return new DataverseReservationService({
      orgUrl,
      // Replace both callbacks when you wire up auth — see docs/SETUP.md § Auth.
      getToken: async () => {
        throw new Error(
          "No token provider configured. Wire MSAL (standalone) or the Power SDK (Code App) into services/index.ts.",
        );
      },
      getUser: async () => {
        throw new Error("No identity provider configured. See docs/SETUP.md § Auth.");
      },
    });
  }

  return new MockReservationService();
}

export const service = createService();
