import { redirect } from "next/navigation";

export default function LegacyAnalyzeRoute() {
  redirect("/assets?tab=import");
}
