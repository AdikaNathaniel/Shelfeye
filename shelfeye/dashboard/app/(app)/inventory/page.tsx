"use client";

import { useShelfEye } from "@/components/DataProvider";
import InventoryTable from "@/components/InventoryTable";

export default function InventoryPage() {
  const { data } = useShelfEye();
  return <InventoryTable rows={data?.inventory ?? []} loading={!data} />;
}
