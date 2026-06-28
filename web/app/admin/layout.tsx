import { RequireAuth } from "@/lib/auth";
import { AdminNav } from "@/components/admin-nav";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth roles={["administrador"]}>
      <div className="flex min-h-screen bg-[#EEF1F6]">
        <AdminNav />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </RequireAuth>
  );
}
