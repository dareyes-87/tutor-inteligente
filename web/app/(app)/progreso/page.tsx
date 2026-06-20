import { CAPITULOS, NIVEL_META } from "@/lib/mock";

export default function ProgresoPage() {
  return (
    <div className="px-[38px] py-[34px]">
      {/* Cabecera + stats */}
      <div className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-2xl font-black text-navy">Mi progreso · Ciencias Naturales</div>
          <div className="mt-[3px] text-sm font-bold text-muted-foreground">
            Tu ruta capítulo por capítulo
          </div>
        </div>
        <div className="flex gap-3.5">
          <div className="rounded-2xl border border-border bg-white px-5 py-3 text-center shadow-[0_5px_16px_rgba(30,43,77,.05)]">
            <div className="text-2xl font-black text-brand-green">18</div>
            <div className="text-[11px] font-extrabold text-muted-foreground">ACTIVIDADES</div>
          </div>
          <div className="rounded-2xl border border-border bg-white px-5 py-3 text-center shadow-[0_5px_16px_rgba(30,43,77,.05)]">
            <div className="text-2xl font-black text-brand-orange">52%</div>
            <div className="text-[11px] font-extrabold text-muted-foreground">AVANCE TOTAL</div>
          </div>
        </div>
      </div>

      {/* Capítulos */}
      <div className="flex flex-col gap-3.5">
        {CAPITULOS.map((c, i) => {
          const nv = NIVEL_META[c.nivel];
          return (
            <div
              key={c.name}
              className="flex items-center gap-[22px] rounded-[20px] border border-border bg-white px-6 py-5 shadow-[0_5px_16px_rgba(30,43,77,.05)]"
            >
              <div
                className="grid h-[46px] w-[46px] flex-none place-items-center rounded-[14px] text-lg font-black"
                style={{ background: nv.chipBg, color: nv.chipColor }}
              >
                {i + 1}
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-2.5 flex items-center justify-between">
                  <div className="text-[16.5px] font-extrabold text-navy">{c.name}</div>
                  <div className="text-[12.5px] font-extrabold text-muted-foreground">
                    {c.done} actividades
                  </div>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-[#ECE7DE]">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${c.pct}%`, background: nv.bar }}
                  />
                </div>
              </div>
              <div className="w-[170px] flex-none text-right">
                <span
                  className="inline-block rounded-full px-4 py-2 text-[13px] font-extrabold"
                  style={{ background: nv.chipBg, color: nv.chipColor }}
                >
                  {nv.chip}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
