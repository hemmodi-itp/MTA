"use client";

import { createContext, useContext } from "react";
import type { CurrentUser } from "@/lib/auth/session";

const CurrentUserContext = createContext<CurrentUser | null>(null);

/** The signed-in user, as already resolved by the (app) layout — no extra request. */
export function CurrentUserProvider({ user, children }: { user: CurrentUser; children: React.ReactNode }) {
  return <CurrentUserContext.Provider value={user}>{children}</CurrentUserContext.Provider>;
}

export function useCurrentUser() {
  return useContext(CurrentUserContext);
}
