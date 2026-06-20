import { RequireAuth } from "@/lib/auth";
import { StudentNav } from "@/components/student-nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <div className="flex min-h-screen bg-cream">
        <StudentNav />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </RequireAuth>
  );
}
