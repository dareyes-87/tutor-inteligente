import { createContext, useCallback, useContext, useEffect, useState } from "react";

import {
  ApiError,
  alExpirarSesion,
  getMe,
  getToken,
  getUsuarioGuardado,
  guardarUsuario,
  login as apiLogin,
  logout as apiLogout,
  tokenVencido,
  type Usuario,
} from "@/lib/api";

const AVISO_EXPIRADA = "Tu sesión expiró, vuelve a ingresar.";

interface AuthValue {
  user: Usuario | null;
  loading: boolean;
  /** Mensaje amable para el login (p. ej. sesión expirada); null si no hay. */
  aviso: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Usuario | null>(null);
  const [loading, setLoading] = useState(true);
  const [aviso, setAviso] = useState<string | null>(null);

  // Cualquier 401 del backend (token vencido o inválido) cierra la sesión y vuelve al login.
  useEffect(() => {
    alExpirarSesion(() => {
      setUser(null);
      setAviso(AVISO_EXPIRADA);
    });
    return () => alExpirarSesion(null);
  }, []);

  useEffect(() => {
    let activo = true;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        if (tokenVencido(token)) {
          await apiLogout();
          if (activo) setAviso(AVISO_EXPIRADA);
          return;
        }
        // Sesión restaurada al instante desde el dispositivo; luego se valida contra el backend.
        const guardado = await getUsuarioGuardado();
        if (guardado && activo) {
          setUser(guardado);
          setLoading(false);
        }
        try {
          const me = await getMe();
          await guardarUsuario(me);
          if (activo) setUser(me);
        } catch (err) {
          // 401: ya lo resolvió alExpirarSesion. Sin red o backend dormido: se mantiene la sesión guardada.
          if (!(err instanceof ApiError && err.status === 401) && !guardado && activo) setUser(null);
        }
      } finally {
        if (activo) setLoading(false);
      }
    })();
    return () => {
      activo = false;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    await apiLogin(username, password);
    const me = await getMe();
    await guardarUsuario(me);
    setAviso(null);
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setAviso(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, aviso, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
