import { ESTUDIANTES_DOCENTE, FAQS, LIBROS_DOCENTE, NIVEL_META, inicial } from "@/lib/mock";

export default function DocentePage() {
  return (
    <div className="px-9 py-8">
      <div className="mb-[3px] text-2xl font-black text-navy">Panel docente</div>
      <div className="mb-6 text-sm font-bold text-[#7B8194]">
        Ciencias Naturales · 5to Primaria · 24 estudiantes
      </div>

      <div className="flex items-start gap-6">
        {/* Columna principal */}
        <div className="flex flex-1 flex-col gap-6">
          {/* Libros */}
          <section className="rounded-[18px] border border-[#E6E9F0] bg-white px-6 py-[22px] shadow-[0_5px_16px_rgba(30,43,77,.05)]">
            <div className="mb-4 text-base font-black text-navy">📚 Libros subidos</div>
            <div className="flex flex-col gap-3">
              {LIBROS_DOCENTE.map((b) => (
                <div
                  key={b.title}
                  className="flex items-center gap-3.5 rounded-[14px] bg-[#F7F9FC] px-3.5 py-3"
                >
                  <div
                    className="h-[46px] w-[38px] flex-none rounded-md"
                    style={{ background: b.spine }}
                  />
                  <div className="flex-1">
                    <div className="text-[14.5px] font-extrabold text-navy">{b.title}</div>
                    <div className="text-xs font-bold text-muted-foreground">{b.pages} páginas</div>
                  </div>
                  <div
                    className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-extrabold"
                    style={{ background: b.statBg, color: b.statColor }}
                  >
                    {b.statDot} {b.status}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Estudiantes */}
          <section className="rounded-[18px] border border-[#E6E9F0] bg-white px-6 py-[22px] shadow-[0_5px_16px_rgba(30,43,77,.05)]">
            <div className="mb-4 flex items-center justify-between">
              <div className="text-base font-black text-navy">
                👩‍🎓 Estudiantes · nivel por asignatura
              </div>
              <button className="text-[12.5px] font-extrabold text-brand-blue">Exportar</button>
            </div>
            <div className="flex px-3.5 pb-2.5 text-[11px] font-extrabold tracking-[0.03em] text-muted-foreground">
              <div className="flex-1">ESTUDIANTE</div>
              <div className="w-[110px] text-center">CIENCIAS</div>
              <div className="w-[110px] text-center">MATEMÁT.</div>
              <div className="w-[110px] text-center">LENGUAJE</div>
            </div>
            <div className="flex flex-col gap-2">
              {ESTUDIANTES_DOCENTE.map((st) => (
                <div
                  key={st.name}
                  className="flex items-center rounded-xl bg-[#F7F9FC] px-3.5 py-2.5"
                >
                  <div className="flex flex-1 items-center gap-[11px]">
                    <div
                      className="grid h-[34px] w-[34px] place-items-center rounded-full text-[13px] font-black text-white"
                      style={{ background: st.av }}
                    >
                      {inicial(st.name)}
                    </div>
                    <span className="text-sm font-extrabold text-navy">{st.name}</span>
                  </div>
                  {st.niveles.map((nivel, idx) => (
                    <div key={idx} className="flex w-[110px] justify-center">
                      <span
                        className="h-[18px] w-[18px] rounded-full"
                        style={{
                          background: NIVEL_META[nivel].dot,
                          boxShadow: `0 0 0 4px ${NIVEL_META[nivel].chipBg}`,
                        }}
                      />
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div className="mt-3.5 flex gap-[18px] px-3.5 text-[11.5px] font-extrabold text-muted-foreground">
              <span>🟢 Domina</span>
              <span>🟡 En proceso</span>
              <span>🔴 Necesita refuerzo</span>
            </div>
          </section>
        </div>

        {/* FAQ */}
        <aside className="w-[360px] flex-none rounded-[18px] border border-[#E6E9F0] bg-white px-6 py-[22px] shadow-[0_5px_16px_rgba(30,43,77,.05)]">
          <div className="mb-1 text-base font-black text-navy">❓ Preguntas frecuentes</div>
          <div className="mb-4 text-[12.5px] font-bold text-muted-foreground">
            Lo que más preguntan tus estudiantes al tutor.
          </div>
          <div className="flex flex-col gap-3">
            {FAQS.map((f) => (
              <div
                key={f.q}
                className="rounded-[14px] bg-[#F7F9FC] px-4 py-3.5"
                style={{ borderLeft: `4px solid ${f.accent}` }}
              >
                <div className="text-sm font-extrabold leading-tight text-navy">{f.q}</div>
                <div className="mt-1.5 text-xs font-extrabold text-muted-foreground">
                  Preguntada {f.count} veces · {f.topic}
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
