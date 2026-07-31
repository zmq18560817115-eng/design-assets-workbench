export type WorkbenchRole = "designer" | "admin";

export const designerNavigation = [
  { href: "/", label: "工作台" },
  { href: "/assets", label: "素材中心" },
  { href: "/patterns", label: "排版知识" },
  { href: "/requirements", label: "业务检索" },
];

export const adminNavigation = [
  { href: "/admin/analysis-evaluation", label: "AI拆解校准" },
  { href: "/layout-search/evaluation", label: "业务检索验收" },
  { href: "/admin/analysis-evaluation/datasets", label: "数据集管理" },
  { href: "/admin/analysis-versions", label: "Prompt与校验版本" },
  { href: "/admin/analysis-evaluation/runs", label: "运行历史" },
];

export function configuredRole(): WorkbenchRole {
  return process.env.NEXT_PUBLIC_WORKBENCH_ROLE === "admin" ? "admin" : "designer";
}
