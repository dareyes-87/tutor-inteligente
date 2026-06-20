import { RequireAuth } from "@/lib/auth";
import { TeacherNav } from "@/components/teacher-nav";

export default function DocenteLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <div className="flex min-h-screen bg-[#F4F6FA]">
        <TeacherNav />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </RequireAuth>
  );
}
