# 检索评测（Retrieval Eval）

把"检索准确率达标"从一句话变成一个**可复现、可回归守护的数字**。这是路线图
阶段二 → 阶段三的门槛，也是后续任何排序/检索训练之前必须先立起来的评价标尺。

> 本目录**不训练任何模型**，只度量当前 `/match` 的检索质量。

## 是什么

- `metrics.py` — Recall@K / MRR / nDCG@K。
- `harness.py` — 用未入库的需求对象调 `crud.match_business_requirement`，逐条算指标并聚合。
- `run_eval.py` — CLI，连真实数据库跑评测、打印并可导出 md/json 报告。
- `eval_set_v1.json` — 金标准评测集（需人工填写）。

## 金标准评测集怎么建

1. 从真实历史需求里抽 **50~100 条**，覆盖主要场景。
2. 每条由 **2 名设计负责人独立标注**"正确参考"（真实的 `pattern` / `case` id），
   取交集，分歧仲裁。
3. 填进 `eval_set_v1.json` 的 `items`：
   - `requirement` 是需求本身的结构化字段；
   - `relevant.patterns` / `relevant.cases` 是金标准 id。
     支持 `[id, ...]`（相关度=1）或 `{"id": grade}`（分级，用于 nDCG）。
4. 冻结、纳入版本管理。以后每次改检索逻辑都对**同一份**评测集复算，数字可比。

`id` 以下划线开头的条目（如模板/说明）会被自动跳过；`relevant` 为空的条目不计入指标。

## 怎么跑

```bash
cd backend
python -m evaluation.run_eval
# 指定评测集与 K、导出报告：
python -m evaluation.run_eval --eval-set evaluation/eval_set_v1.json --k 3,5 \
    --md-out evaluation/report.md --json-out evaluation/report.json
```

评测连接与应用相同的 `DATABASE_URL`，因此跑在真实的已确认模式/案例数据上。
先用 1~2 条种子样本跑通链路，再扩到完整评测集。

## 指标怎么读

| 指标 | 含义 | 越高越好 |
|---|---|---|
| `recall@K` | top-K 命中金标准参考的比例 | ✓ |
| `mrr` | 第一个命中的倒数排名（好答案是否排在前面） | ✓ |
| `ndcg@K` | 带分级相关度的排序质量 | ✓ |

模式检索与案例检索**分开度量、分开聚合**（对应 `/match` 的两条结果）。

## 回归守护

`backend/tests/test_eval_harness.py` 用自建种子库验证指标计算正确，并作为
基线守护——后续改检索逻辑若让已知相关项掉出 top-K，测试会报警。

## 后续（当检索排序引入学习信号时）

当检索侧引入反馈重排或排序模型后，可在 `harness.evaluate` 外层加一个
"开/关"对照跑，用同一份评测集证明新信号是否带来 nDCG/MRR 增益，达标才上线。
