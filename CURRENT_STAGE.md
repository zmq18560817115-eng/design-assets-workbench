# 当前开发阶段

## P3.2-C：公司素材驱动的拆解校准闭环

当前已建立独立的 AI 拆解校准数据集、不可变 Prompt/Validator 版本、Calibration
诊断、版本冻结和密封 Holdout 流程。普通设计师入口已收口为工作台、素材中心、
排版知识和业务检索。

业务判断仍须追溯到公司成品案例、已确认 `LayoutBlueprint`、已确认
`LayoutPattern`、业务规则和人工审核记录。当前阶段是大批量拆解和知识沉淀，
不是模型微调，也不生成最终设计图。

## Task 4.1 阶段结论

Task 4.1B 的真实业务检索验收工作台已完成。设计负责人可以维护未冻结 Ground Truth、查看案例/蓝图/模式证据、执行冻结前准备度检查、导入导出验收包，并分别查看 calibration 与 holdout 结果。冻结后只能创建新版本继续调整。

当前主线为：素材上传 → AI拆解 → 蓝图人工确认 → 排版模式沉淀 → 真实需求 → 冻结 Ground Truth → 校准集调试 → 留出集验收。只有真实验收 `passed` 后才能进入多案例排版方向。

冻结式检索验收工具已经完成收口，包括数据集版本、Ground Truth 工作台、不可逆冻结、事务导入、加权指标、真实数据准备度和 `not_ready / failed / passed` 三态门禁。

当前结论是“可以开始准备真实业务验收”，不是“真实业务验收已经通过”。真实数据必须满足 50 个 verified 公司案例、5 个 verified 模式、10 条 confirmed 真实需求及 7/3 calibration/holdout 划分。calibration 只用于校准；holdout 不得反复查看并用于调权。全部门禁通过后才能进入多案例排版方向阶段。

`ENABLE_LAYOUT_DIRECTIONS=false` 为默认设置。当前不训练偏好模型、不生成最终设计图，legacy 数据与接口含义保持不变。

## 当前产品定位

AI业务排版知识库与意向方向生成系统。

## 核心业务主线

素材上传 → AI拆解 → LayoutBlueprint → 人工校正与确认 →
LayoutPattern候选发现与审核 → BusinessRequirement →
已确认模式/案例检索 → 设计师相关性反馈与准确率评估。

## 已完成能力

- 素材单张上传、批量导入、来源与产品分类。
- AI图片拆解以及明确标记的本地 fallback。
- LayoutBlueprint 标准化、版本、人工校正和确认。
- BusinessRequirement 基础数据结构及草稿、编辑、确认。
- 从已确认蓝图人工沉淀排版模式的兼容能力。

## 当前正式能力

- 最新 verified 蓝图作为模式发现证据。
- 确定性结构相似度、候选分组、平均骨架和稳定模式编码。
- 候选模式证据、可信度、人工确认、停用与历史数据保护。
- 结构化业务需求应用必需和禁止模块约束。
- 已确认排版模式和已确认真实案例的确定性、可解释检索。
- 参考图片临时蓝图、运行快照、相关性反馈和 Precision 评估。

## 实验性能力

- 旧 `/match` 场景匹配接口。
- 三个排版方向。
- 方向反馈。

上述旧实验能力保留代码和数据，但不属于 P3 正式检索主线。

## Legacy兼容能力

Preference、Training、Company Profile、Service Run、Project Review
属于 legacy。相关接口和数据表暂时保留以兼容历史数据，但不参与
LayoutPattern 自动发现，也不提供当前产品决策权重。

## 当前阶段开发目标

使用真实业务需求检索已确认模式和案例，返回分项得分、硬约束、证据与适配风险，
并用人工相关性反馈评估 Precision@5 和 Precision@10。

## 下一阶段但暂不执行

- 50 张公司真实素材与 10 条真实需求的正式业务验收。
- 多案例融合方向。
- 方向采纳反馈闭环。
- 排序模型或视觉模型训练。
- 最终设计图生成。

## 禁止偏离事项

- 不根据颜色或风格出现频率推断公司偏好。
- 不读取 PreferenceEvent 或旧推荐权重进行模式归纳。
- 不训练或微调模型。
- 不接入最终图片生成。
- 不引入 PostgreSQL、pgvector、复杂权限或复杂拖拽画布。

## 验收门槛

- 只有每个真实案例最新的合法 verified 蓝图参与归纳。
- 少于 3 个不同案例不生成候选。
- 15 个隔离 fixture 案例能稳定形成至少 5 个候选模式。
- dry-run 不写库，重复重建不重复新增。
- verified、disabled 和人工模式不被自动覆盖。
- 候选模式能追溯来源案例、蓝图、相似度和参与模块。
- 禁止模块命中结果只进入排除区，正常结果违规数为 0。
- 检索结果分项之和等于总分并可追溯来源。
- 隔离 Fixture 的 Precision@5 和 Precision@10 均不低于 0.60。
- 后端测试、Python 编译、前端 lint 和 build 全部通过。

## P3.2-A 证据边界

公司成品与外部素材是两种不同证据。`company_published` 只能证明作品真实发布；
只有人工审核才能设置 `company_recommended` 或项目 `is_gold`。
`external_reference` 仅用于结构、风格或素材参考，不能作为公司业务标准。
当前工作是批量拆解与知识沉淀，不是模型微调，也不开发多案例方向、设计审核、
排序模型或图片生成。正式主线保持 LayoutBlueprint、LayoutPattern 和 layout_search。
