import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { api, ApiError, onUnauthorized, setCsrf } from "./api";
import type { User } from "./types";

type Me = { user: User; csrf_token: string; unread_notifications: number };
type Session = {
  user?: User; loading: boolean; unread: number;
  login: (username: string, password: string) => Promise<void>;
  demoLogin: (username: string) => Promise<void>;
  logout: () => Promise<void>;
};
const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const me = useQuery({
    queryKey: ["me"], retry: false, refetchInterval: 30_000,
    queryFn: async () => {
      try {
        const m = await api.get<Me>("/auth/me");
        setCsrf(m.csrf_token);
        return m;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) { setCsrf(null); return null; }
        throw e;
      }
    },
  });
  useEffect(() => {
    const off = onUnauthorized(() => { qc.setQueryData(["me"], null); });
    return () => { off(); };
  }, [qc]);
  const resetOthers = () => qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
  const after = async (r: { csrf_token: string }) => {
    setCsrf(r.csrf_token);
    const m = await api.get<Me>("/auth/me");
    setCsrf(m.csrf_token);
    resetOthers();
    qc.setQueryData(["me"], m);
  };
  const value: Session = {
    user: me.data?.user, loading: me.isLoading, unread: me.data?.unread_notifications ?? 0,
    login: async (username, password) => after(await api.post<{ csrf_token: string }>("/auth/login", { username, password })),
    demoLogin: async (username) => after(await api.post<{ csrf_token: string }>("/auth/demo-login", { username })),
    logout: async () => {
      await api.post("/auth/logout").catch(() => undefined);
      setCsrf(null);
      resetOthers();
      qc.setQueryData(["me"], null);
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession() {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside provider");
  return s;
}
