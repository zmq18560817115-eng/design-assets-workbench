import { redirect } from "next/navigation";

export default function LegacyBatchRoute() {
  redirect("/assets?tab=import&mode=batch");
}
