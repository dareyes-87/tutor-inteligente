"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ApiError, adminDashboard, type DashboardAdmin } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const ESTADO_LIBRO: Record<string, { bg: string; color: string; label: string }> = {
  completado: { bg: "#E9F9EF", color: "#16A34A", label: "Completado" },
  procesando: { bg: "#FEF6E7", color: "#D97706", label: "Procesando…" },
  pendiente: { bg: "#F1EDE5", color: "#8A8F9C", label: "Pendiente" },
  error: { bg: "#FDECEC", color: "#DC2626", label: "Error" },
};

export default function AdminDashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardAdmin | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let activo = true;
    adminDashboard()
      .then((d) => activo && setData(d))
      .catch((err) => activo && toast.error(err instanceof ApiError ? err.message : "No se pudo cargar el dashboard"))
      .finally(() => activo && setCargando(false));
    return () => {
      activo = false;
    };
  }, []);

  const cards = [
    { label: "Estudiantes activos", val: data?.total_estudiantes, icon: "👩‍🎓" },
    { label: "Docentes activos", val: data?.total_docentes, icon: "👨‍🏫" },
    { label: "Grados", val: data?.total_grados, icon: "🏫" },
    { label: "Asignaturas", val: data?.total_asignaturas, icon: "📚" },
    { label: "Libros", val: data?.total_libros, icon: "📕" },
    { label: "Lecciones", val: data?.total_lecciones, icon: "🗺️" },
    { label: "Fragmentos", val: data?.total_fragmentos, icon: "🧩" },
    { label: "Activos hoy", val: data?.estudiantes_activos_hoy, icon: "🔥" },
  ];

  const est = data?.libro_mas_reciente
    ? ESTADO_LIBRO[data.libro_mas_reciente.estado] ?? ESTADO_LIBRO.pendiente
    : null;

  return (
    <div className="px-9 py-8">
      <div className="mb-1 text-2xl font-black text-slate-900">Dashboard</div>
      <div className="mb-6 text-sm font-bold text-slate-500">
        {user ? `${user.nombre} ${user.apellido}` : "Administrador"} · Oasis Christian School
      </div>

      {cargando ? (
        <div className="py-10 text-center text-sm font-bold text-slate-400">Cargando…</div>
      ) : (
        <>
          <div className="mb-6 grid grid-cols-4 gap-4">
            {cards.map((c) => (
              <div
                key={c.label}
                className="rounded-[18px] border border-slate-200 bg-white px-6 py-5 shadow-[0_5px_16px_rgba(30,43,77,.05)]"
              >
                <div className="mb-2 text-xl">{c.icon}</div>
                <div className="text-[30px] font-black leading-none text-slate-900">{c.val ?? "—"}</div>
                <div className="mt-1.5 text-xs font-extrabold uppercase tracking-wide text-slate-400">
                  {c.label}
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Progreso general */}
            <div className="rounded-[18px] border border-slate-200 bg-white px-6 py-6 shadow-[0_5px_16px_rgba(30,43,77,.05)]">
              <div className="mb-3 text-sm font-extrabold uppercase tracking-wide text-slate-400">
                Progreso general del colegio
              </div>
              <div className="mb-3 text-[40px] font-black leading-none text-slate-900">
                {Math.round(data?.progreso_general ?? 0)}%
              </div>
              <div className="h-3 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-slate-700"
                  style={{ width: `${Math.min(100, data?.progreso_general ?? 0)}%` }}
                />
              </div>
              <div className="mt-2 text-xs font-bold text-slate-500">
                Promedio de avance (por niveles) de todos los estudiantes activos.
              </div>
            </div>

            {/* Libro más reciente */}
            <div className="rounded-[18px] border border-slate-200 bg-white px-6 py-6 shadow-[0_5px_16px_rgba(30,43,77,.05)]">
              <div className="mb-3 text-sm font-extrabold uppercase tracking-wide text-slate-400">
                Libro más reciente
              </div>
              {data?.libro_mas_reciente ? (
                <div className="flex items-center gap-4">
                  <div className="grid h-12 w-10 flex-none place-items-center rounded-md bg-slate-800 text-lg">
                    📕
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[15px] font-extrabold text-slate-900">
                      {data.libro_mas_reciente.titulo}
                    </div>
                    <div className="text-xs font-bold text-slate-500">
                      {new Date(data.libro_mas_reciente.fecha_subida).toLocaleDateString("es-GT")}
                    </div>
                  </div>
                  {est && (
                    <span
                      className="flex-none rounded-full px-3 py-1.5 text-[11.5px] font-extrabold"
                      style={{ background: est.bg, color: est.color }}
                    >
                      {est.label}
                    </span>
                  )}
                </div>
              ) : (
                <div className="text-sm font-bold text-slate-400">Aún no hay libros subidos.</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
