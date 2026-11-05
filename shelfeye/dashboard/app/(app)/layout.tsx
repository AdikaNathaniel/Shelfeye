import AppShell from "@/components/AppShell";
import DataProvider from "@/components/DataProvider";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <DataProvider>
      <AppShell>{children}</AppShell>
    </DataProvider>
  );
}
