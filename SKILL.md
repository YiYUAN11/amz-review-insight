---
name: amz-review-insight
description: 分析亚马逊买家之声退货报告与商品评论，自动提炼部件维度、生成多级标签与统计，产出可视化网页（中英对照·白天主题）、Excel 与 Markdown 报告。当用户提供亚马逊退货/评论导出文件（xlsx）并要求做买家洞察、退货原因分析、差评分析、VOA 分析、痛点拆解、评论洞察、竞品差评分析时使用。
---

# 亚马逊退货 & 评论洞察分析

把「买家之声退货导出报告」+「商品买家评论」两类文件，转成一套完整的洞察交付物：
观点拆分 → 多级标签 → 统计 → 可视化网页 → Excel → 报告。

## 何时使用

用户提供以下任一文件并要求做退货/评论/差评分析、买家之声分析、VOA 分析、
评论洞察、痛点分析时：

- 亚马逊买家之声退货导出（voice of the customer）xlsx
- 亚马逊商品评论导出 xlsx
- 第三方平台的评论导出（卖家精灵、领英、卖家之家等）

## 核心原则（不可妥协）

1. **忠于原文**：所有观点必须是原文截取，不做语义扩充、不臆测缺陷部位。
2. **一条多感受必须拆**：例「手感好但是支架不好用」→ 拆成「手感好(正向)」「支架不好用(负面)」。
3. **平台下拉理由单独成列**：`Not as Expected`、`Defective` 等是固定选项，没有具体落点，
   单独标为「平台理由」，**不参与部件归因**，不要为凑归因而强行拆解。
4. **分母永远写清楚**：占全部观点 / 占该大类内部 / 占该来源内部，三者不可混用。
5. **百分比两位小数**。
6. **样本太小要明说**：不要过度推断根因。
7. **语义模糊标「归类存疑」**，不硬猜。

## 工作流

### 第 1 步 · 探查输入文件

```bash
python scripts/run.py --probe <文件路径...>
```

输出每个文件的工作表、表头、行数、**文本列候选**。这决定 `text_columns` 怎么填。

### 第 2 步 · 自动提炼部件维度（关键步骤）

```bash
python scripts/discover.py --config taxonomy.json --out candidates.json
```

从语料里挖掘**这个品类的部件/对象**（折叠屏壳是「铰链/支架/磁吸环」，
耳机是「耳塞/电池/充电仓」，保温杯是「杯盖/密封圈/内胆」……）。
输出候选词 + 与各失效现象的共现次数 + 原始证据句。

> **脚本负责统计，语义判断交给 Agent。**
> 必须阅读候选与证据样本，把**真部件**写进 taxonomy 配置。跳过这步 = 后面全是错的。

### 第 3 步 · 写 taxonomy 配置

复制 `examples/taxonomy.example.json` 改写。详见 `references/taxonomy-guide.md`。

三块必填：
- `parts`：本品类的部件（中文名 + 英文别名 + 归属一级大类 + 该部件**专属**的失效模式）
- `failure_modes`：失效现象库（断裂/松动/撑不住/过薄/不贴合/充不进电…跨品类复用）
- `inputs`：文件路径

**通用失效模式**（断裂脱落、贴合不好、做工粗糙…）放进 `failure_modes`，
再用 `global_modes: ["断裂脱落", "不贴合", ...]` 声明它们对所有部件生效；
`parts[].modes` 只写**该部件特有**的模式。这样配置量能减少一半以上。

### 第 3.5 步 · 配置自检（必做，30 秒）

```bash
python scripts/validate_taxonomy.py --config taxonomy.json
```

检查结构完整性、**模式引用是否存在**（静默失效的高发点）、正则能否编译、
一级大类是否合法、命中率预检、词典规模。有 ERROR 必须先修再往下跑。

### 第 4 步 · 跑全流程

```bash
python scripts/run.py --config taxonomy.json --out-dir ./output --title "报告标题"
```

产出（都在 `--out-dir`）：
- `*_可视化.html` — 单文件网页，离线可开，白天主题，中英对照
- `*_洞察分析.xlsx` — 7 个工作表：二级标签细分 / 总览 / 部件维度 / 原文证据墙 /
  全量明细 / **交叉表_部件×模式×来源** / **优先级行动清单**
- `*_分析报告.md` — Markdown 报告（含「普遍 vs 个案」判定与优先级）

### 第 5 步 · 翻译长句（可选但强烈建议）

规则翻译只覆盖**短评价句**（≤8 词）。长句交给 Agent 翻：

```bash
# ① 导出待翻译清单（JSONL）
python scripts/run.py --config taxonomy.json --out-dir ./output --export-zh-todo zh_todo.jsonl
# ② Agent 逐条填好 "zh" 字段，另存 zh_map.jsonl
# ③ 回灌译文后重新出报告
python scripts/run.py --config taxonomy.json --out-dir ./output --zh zh_map.jsonl
```

**不要**用逐词拼的规则翻译长句——实测会产生 70%+ 的中英混排，
比直接保留英文更糟。宁可高质中文，要么忠实英文，不要「看着像中文读不通」。

### 第 6 步 · 复核并迭代（必做）

```bash
python scripts/run.py --config taxonomy.json --out-dir ./output --audit
```

`--audit` 随机抽样 60 条逐条打印 `原文 → 归类`，并统计未归类比例。
**Agent 读这些样本，修正 taxonomy 后重跑**，直到未归类占比降到可接受水平。
规则写错的代价是整份报告失真，这一步不能跳。

### 第 7 步 · 质量门禁（交付前）

```bash
python scripts/run.py --config taxonomy.json --out-dir ./output --strict
```

`--strict` 会打印质量评估并在不达标时返回非 0 退出码：

| 指标 | 阈值 | 不达标怎么办 |
|---|---|---|
| 未归类负面占比 | ≤ 25% | 补 `failure_modes` 的 patterns |
| 识别出具体部件 | 越高越好 | 补 `parts` 的 aliases |
| 命中具体失效模式 | 越高越好 | 同上 |
| 译文覆盖率 | ≥ 60% | 用 `--export-zh-todo` 补翻 |
| 中英混排占比 | ≤ 15% | 检查是否误用规则翻译长句 |

> 指标口径：**部件识别率 / 模式命中率** 的分母是**非平台理由**的负面观点数，
> 平台下拉理由（无具体落点）不参与归因。

## 标签体系结构

```
一级大类（9 类固定，跨品类通用）
  └─ 二级标签（自动生成：部件 × 失效大类）
       └─ 三级细分（具体失效模式，带现象描述 + 原文证据）
            └─ 买家原文（中文译文 + 英文原文对照）
```

情绪标签（正向/负面/中性）与「有无明确具象点」是**正交的横切维度**，
每个观点都同时具备这两项属性。

一级大类（9 类固定）：
`Listing预期不符`｜`结构/功能配件`｜`产品做工&材质`｜`尺寸贴合`｜
`外观手感`｜`包装物流`｜`使用体验`｜`性价比`｜`其他`

## 换粒度 / 换风格

- **更细**：在 `failure_modes` 里加模式，或给 `parts` 配更具体的 `modes`
- **换一级大类**：改 `failure_modes[].cat1` 与 `parts[].cat1`
- **换视觉**：改 `templates/web/` 下的 CSS/JS，不影响分析逻辑
- **加品类专属词**：`extra_translations`

## 目录

```
scripts/run.py                 端到端主流程
scripts/validate_taxonomy.py   配置自检（跑之前先跑它）
scripts/discover.py            自动提炼部件候选
scripts/lib/engine.py          拆分/分类/统计引擎
scripts/lib/discover_lib.py    候选挖掘算法
scripts/lib/dict_zh.py         通用英中词典
scripts/lib/translate.py       翻译器（短句规则 + 长句回灌）
scripts/lib/io_html.py         网页输出
scripts/lib/io_excel.py        Excel 输出
scripts/lib/io_md.py           报告输出
templates/web/                 网页模板（改样式改这里）
references/taxonomy-guide.md   怎么写 taxonomy
references/output-spec.md       交付物规格与口径
examples/                      可直接改的 taxonomy 样例
```

## 翻译

买家原文默认**中英对照**：中文为主（深色加粗），英文原文小字斜体保留在下方。
词典驱动（`scripts/lib/dict_zh.py`），只覆盖电商通用词。
品类专属词汇补到 `taxonomy.json` 的 `extra_translations`。

**翻译分工**：短评价句（≤8 词）走规则翻译；长句走 Agent 回灌
（`--export-zh-todo` → Agent 填 `zh` → `--zh` 回灌）。
理由见「常见坑」最后一条。

## 常见坑

- **文本列选错**：退货报告里「反馈内容」和「商品标题」都是长文本。用 `--probe` 看候选，
  在 `text_columns` 里显式指定。
- **评论表混了多列**：星级列用于辅助情感判定，脚本会自动找 `星级/rating/star/score`。
- **说明页混进数据**：卖家精灵导出常带 `Note` 工作表（客服电话/插件指南），
  脚本会自动跳过；若没跳过，在 `text_columns` 里排除该表名。
- **部件别名漏了**：买家可能写「magsafe」「磁吸」「MagSafe 环」，`aliases` 要把各种写法都列上。
- **模式被部件抢走**：用 `parts[].modes` 限定某部件只可能出现的模式，避免误配。
- **`parts[].modes` 引用了不存在的模式**：不会报错，只会永远匹配不上——
  这就是 `validate_taxonomy.py` 存在的原因。
- **叙述句被当成观点**：「I've used other cases…」「I came from OtterBox…」是背景交代，
  不是对本品的评价。引擎已内置叙述句过滤，但仍要用 `--audit` 抽查确认。
- **长句用规则翻译**：会产生大量中英混排（实测 70%+）。长句必须走 Agent 回灌。
