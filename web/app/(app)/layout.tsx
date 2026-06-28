import { RequireAuth } from "@/lib/auth";
import { StudentNav } from "@/components/student-nav";
import { StudentTabBar } from "@/components/student-tabbar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth roles={["estudiante"]}>
      <div className="flex min-h-screen bg-cream">
        <StudentNav />
        {/* pb-16 reserva el alto de la barra de pestañas en móvil; en md:+ desaparece. */}
        <main className="flex-1 overflow-auto pb-16 md:pb-0">{children}</main>
        <StudentTabBar />
      </div>
    </RequireAuth>
  );
}
