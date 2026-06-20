import { PODIO, RANKING_RESTO } from "@/lib/mock";

export default function RankingPage() {
  return (
    <div className="px-[38px] py-[34px]">
      {/* Cabecera + tabs */}
      <div className="mb-[22px] flex items-center justify-between">
        <div className="text-2xl font-black text-navy">Tabla de posiciones 🏆</div>
        <div className="flex gap-2 rounded-[14px] bg-[#F3ECE1] p-[5px]">
          <div className="rounded-[11px] bg-white px-[22px] py-[9px] text-sm font-extrabold text-navy shadow-[0_2px_6px_rgba(30,43,77,.08)]">
            Mi salón
          </div>
          <div className="rounded-[11px] px-[22px] py-[9px] text-sm font-extrabold text-muted-foreground">
            Mi grado
          </div>
        </div>
      </div>

      {/* Podio */}
      <div className="mb-[26px] flex h-[240px] items-end justify-center gap-5 rounded-[20px] bg-gradient-to-b from-[#FFF6EB] to-transparent pt-[18px]">
        {PODIO.map((p) => (
          <div key={p.pos} className="w-40 text-center">
            <div className="text-[30px]">{p.medal}</div>
            <div
              className="mx-auto mb-2 mt-0.5 grid h-16 w-16 place-items-center overflow-hidden rounded-full bg-[#EDE7DD] text-[22px] font-black text-navy"
              style={{ boxShadow: `0 0 0 4px ${p.ring}` }}
            >
              {p.initial}
            </div>
            <div className="text-sm font-black text-navy">{p.name}</div>
            <div className="mb-2 text-xs font-extrabold text-muted-foreground">{p.pts} pts</div>
            <div
              className="grid place-items-start justify-center rounded-t-2xl pt-3.5 text-[30px] font-black text-navy"
              style={{ background: p.bg, height: p.tall }}
            >
              {p.pos}
            </div>
          </div>
        ))}
      </div>

      {/* Lista */}
      <div className="flex flex-col gap-2.5">
        {RANKING_RESTO.map((r) => (
          <div
            key={r.pos}
            className="flex items-center gap-[18px] rounded-2xl border border-border bg-white px-[22px] py-3.5 shadow-[0_4px_12px_rgba(30,43,77,.04)]"
          >
            <div className="w-[30px] text-[17px] font-black text-muted-foreground">{r.pos}</div>
            <div
              className="grid h-[42px] w-[42px] flex-none place-items-center rounded-full text-base font-black text-white"
              style={{ background: r.avBg }}
            >
              {r.initial}
            </div>
            <div className="flex-1 text-base font-extrabold text-navy">{r.name}</div>
            <div className="text-sm font-extrabold text-brand-orange">🔥 {r.streak}</div>
            <div className="w-[110px] text-right text-base font-black text-navy">
              {r.pts} <span className="text-xs text-muted-foreground">pts</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
