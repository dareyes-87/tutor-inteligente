"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { homeForRole } from "@/lib/constants";

/** Entrada: redirige al inicio según el rol si hay sesión, o al login si no. */
export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? homeForRole(user.rol) : "/login");
  }, [user, loading, router]);

  return (
    <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
      Cargando…
    </div>
  );
}
