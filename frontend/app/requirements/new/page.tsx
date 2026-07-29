"use client";
import { useRouter } from "next/navigation";
import { BusinessRequirementForm, emptyRequirement } from "@/components/business-requirement-form";
import { api } from "@/lib/api";

export default function NewRequirementPage() {
  const router = useRouter();
  return <div><h1 className="mb-6 text-3xl font-bold">创建业务需求</h1>
    <BusinessRequirementForm value={emptyRequirement} submitLabel="保存草稿" onSubmit={async (value)=>{
      const created = await api.createBusinessRequirement({...value, status:"draft"});
      router.push(`/requirements/${created.id}`);
    }} />
  </div>;
}
