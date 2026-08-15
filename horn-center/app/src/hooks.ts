import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Policy, Reservation, Resource, Student } from "./types";
import { DEFAULT_POLICY } from "./lib/policy";
import { nextBookableDay } from "./lib/rules";
import { endOfWeek, startOfDay, startOfWeek } from "./lib/time";
import { service } from "./services";
import { BookingError } from "./services/types";

export interface HornCenterState {
  loading: boolean;
  error: string | null;
  user: Student | null;
  policy: Policy;
  resources: Resource[];
  /** Every active reservation in the selected week — the availability picture. */
  weekReservations: Reservation[];
  /** The signed-in student's full history, past and future. */
  myReservations: Reservation[];
  /** Union used as validation context so weekly/active caps see everything. */
  validationSet: Reservation[];
  day: Date;
  setDay: (day: Date) => void;
  refresh: () => Promise<void>;
  book: (input: {
    resourceId: string;
    startsAt: string;
    endsAt: string;
    purpose?: string;
  }) => Promise<void>;
  cancel: (id: string) => Promise<void>;
  checkIn: (id: string) => Promise<void>;
}

export function useHornCenter(): HornCenterState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<Student | null>(null);
  const [policy, setPolicy] = useState<Policy>(DEFAULT_POLICY);
  const [resources, setResources] = useState<Resource[]>([]);
  const [weekReservations, setWeekReservations] = useState<Reservation[]>([]);
  const [myReservations, setMyReservations] = useState<Reservation[]>([]);
  const [day, setDayState] = useState<Date>(() => startOfDay(new Date()));
  // The opening day is chosen once, from the loaded policy — after that the
  // student's own date choice wins, even if they pick a closed day.
  const dayInitialized = useRef(false);

  const load = useCallback(
    async (forDay: Date) => {
      setError(null);
      try {
        const [me, activePolicy, allResources] = await Promise.all([
          service.getCurrentUser(),
          service.getPolicy(),
          service.listResources(),
        ]);

        if (!dayInitialized.current) {
          dayInitialized.current = true;
          const opening = nextBookableDay(new Date(), activePolicy);
          if (opening.getTime() !== forDay.getTime()) {
            setPolicy(activePolicy);
            setDayState(opening);
            return; // The effect re-runs for the corrected day.
          }
        }

        const [week, mine] = await Promise.all([
          service.listReservations(startOfWeek(forDay), endOfWeek(forDay)),
          service.listMyReservations(me.id),
        ]);
        setUser(me);
        setPolicy(activePolicy);
        setResources(allResources);
        setWeekReservations(week);
        setMyReservations(mine);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load the Horn Center schedule.");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load(day);
  }, [day, load]);

  const setDay = useCallback((next: Date) => setDayState(startOfDay(next)), []);
  const refresh = useCallback(() => load(day), [day, load]);

  const validationSet = useMemo(() => {
    const byId = new Map<string, Reservation>();
    for (const r of [...weekReservations, ...myReservations]) byId.set(r.id, r);
    return [...byId.values()];
  }, [weekReservations, myReservations]);

  const book = useCallback(
    async (input: { resourceId: string; startsAt: string; endsAt: string; purpose?: string }) => {
      if (!user) throw new BookingError("Not signed in.");
      await service.create({ ...input, studentId: user.id });
      await load(day);
    },
    [user, day, load],
  );

  const cancel = useCallback(
    async (id: string) => {
      await service.cancel(id);
      await load(day);
    },
    [day, load],
  );

  const checkIn = useCallback(
    async (id: string) => {
      await service.checkIn(id);
      await load(day);
    },
    [day, load],
  );

  return {
    loading,
    error,
    user,
    policy,
    resources,
    weekReservations,
    myReservations,
    validationSet,
    day,
    setDay,
    refresh,
    book,
    cancel,
    checkIn,
  };
}

/** Re-renders on an interval so "now"-relative UI (the kiosk) stays truthful. */
export function useNow(intervalMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
