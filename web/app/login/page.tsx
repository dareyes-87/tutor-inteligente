"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { homeForRole } from "@/lib/constants";
import { Mascota } from "@/components/mascota";

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Si ya hay sesión, no mostrar el login.
  useEffect(() => {
    if (!loading && user) router.replace(homeForRole(user.rol));
  }, [loading, user, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const me = await login(username.trim(), password);
      toast.success("Sesión iniciada");
      router.replace(homeForRole(me.rol));
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.status === 401
            ? "Usuario o contraseña incorrectos"
            : err.message
          : "No se pudo conectar con el servidor";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden bg-cream p-4">
      <div className="bg-dots pointer-events-none absolute inset-0 opacity-60" />

      <div className="relative flex w-full max-w-[880px] overflow-hidden rounded-[32px] border border-[#F0EBE3] bg-white shadow-[0_20px_50px_rgba(30,43,77,.14)]">
        {/* Panel mascota */}
        <div className="relative hidden w-[380px] flex-none items-end justify-center overflow-hidden bg-navy md:flex">
          <div className="absolute left-0 right-0 top-[34px] flex justify-center">
            <div className="relative rounded-[18px] bg-white px-5 py-3 text-base font-extrabold text-navy shadow-[0_8px_20px_rgba(0,0,0,.2)]">
              ¡Hola! ¿Listo para aprender?
              <div className="absolute -bottom-2 left-9 h-[18px] w-[18px] rotate-45 bg-white" />
            </div>
          </div>
          <div className="animate-floaty pb-2">
            <Mascota size={340} alt="Tigre saludando" className="w-[340px]" />
          </div>
        </div>

        {/* Formulario */}
        <div className="flex flex-1 flex-col justify-center px-12 py-[46px]">
          <div className="mb-[26px] flex items-center gap-3">
            <img
              src="/dash.png"
              alt="Oasis Christian School"
              className="h-[90px] w-[90px] flex-none object-contain"
            />
            <div className="leading-[1.05]">
              <div className="text-[17px] font-black text-navy">Oasis Christian School</div>
              <div className="text-[11px] font-bold tracking-[0.05em] text-muted-foreground">
                TUTOR INTELIGENTE
              </div>
            </div>
          </div>

          <h2 className="mb-1 text-[28px] font-black text-navy">¡Bienvenido!</h2>
          <p className="mb-6 text-[14.5px] font-semibold text-muted-foreground">
            Ingresa para seguir aprendiendo.
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col">
            <label htmlFor="username" className="mb-[7px] block text-[13px] font-extrabold text-[#5A6170]">
              Usuario
            </label>
            <div className="mb-[18px] flex items-center gap-2.5 rounded-2xl border-2 border-border bg-muted/50 px-4 py-[14px] focus-within:border-brand-orange">
              <span className="text-[17px]">👤</span>
              <input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="sofia.morales"
                autoComplete="username"
                required
                className="w-full bg-transparent text-[15px] font-semibold text-navy outline-none placeholder:text-[#B6BBC6]"
              />
            </div>

            <label htmlFor="password" className="mb-[7px] block text-[13px] font-extrabold text-[#5A6170]">
              Contraseña
            </label>
            <div className="mb-[26px] flex items-center gap-2.5 rounded-2xl border-2 border-border bg-muted/50 px-4 py-[14px] focus-within:border-brand-orange">
              <span className="text-[17px]">🔒</span>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                required
                className="w-full bg-transparent text-[15px] font-bold text-navy outline-none placeholder:text-[#B6BBC6]"
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="btn-relief rounded-[18px] bg-brand-orange py-[17px] text-center text-lg font-black text-white disabled:opacity-60"
            >
              {submitting ? "Entrando…" : "Entrar 🚀"}
            </button>
          </form>

          <div className="mt-[18px] cursor-pointer text-center text-[13px] font-bold text-brand-blue">
            ¿Olvidaste tu contraseña?
          </div>
        </div>
      </div>
    </div>
  );
}
