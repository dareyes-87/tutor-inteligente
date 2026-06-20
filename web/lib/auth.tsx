"use client";

/**
 * Contexto de autenticación en el cliente.
 * Mantiene el usuario en estado, lo carga desde /auth/me al montar (si hay token)
 * y expone login/logout. Las páginas protegidas usan <RequireAuth>.
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
} from "react";
import { useRouter } from "next/navigation";

import {
  getMe,
  getToken,
  login as apiLogin,
  logout as apiLogout,
  type Usuario,
} from "@/lib/api";

interface AuthContextValue {
  user: Usuario | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<Usuario>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Usuario | null>(null);
  const [loading, setLoading] = useState(true);

  // Al montar: si hay token, intentar recuperar el usuario.
  useEffect(() => {
    let active = true;
    async function load() {
      if (!getToken()) {
        setLoading(false);
        return;
      }
      try {
        const me = await getMe();
        if (active) setUser(me);
      } catch {
        // token inválido/expirado: el cliente API ya lo limpió
        if (active) setUser(null);
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    await apiLogin(username, password);
    const me = await getMe();
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}

/** Envuelve páginas que requieren sesión; redirige a /login si no hay usuario. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Cargando…
      </div>
    );
  }

  return <>{children}</>;
}
