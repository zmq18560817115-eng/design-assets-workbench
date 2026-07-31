import { redirect } from "next/navigation";

export default function LegacyCasesRoute() {
  redirect("/assets?tab=library");
}
