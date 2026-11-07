# 怎么写 taxonomy 配置

taxonomy 是这个技能唯一的「品类知识载体」。引擎不认识折叠屏、不认识耳机——
它只认识你在配置里声明的**部件**和**失效模式**。

---

## 1. inputs 与 text_columns

```json
"inputs": ["D:/data/退货报告.xlsx", "D:/data/评论.xlsx"],
"text_columns": {
  "退货报告.xlsx": "反馈内容",
  "评论明细": "评论原文"
}
```

键可以是**文件名**或**工作表名**（工作表名优先匹配）。
留空 `{}` 时，脚本自动选「非空率高 + 平均长度最长」的那一列——多数情况够用，
但退货报告里「商品标题」也很长，容易选错，**建议显式指定**。

---

## 2. parts（部件）

这是整个体系的地基。部件 = 买家嘴里反复提到的那个**东西**。

```json
{
  "name": "铰链/中轴",
  "aliases": ["hinge", "hinges", "spine", "fold"],
  "cat1": "结构/功能配件",
  "modes": ["无防护", "宣传误导"]
}
```

| 字段 | 作用 | 要点 |
|---|---|---|
| `name` | 中文名，同时用于在原文中直接匹配中文 | 用「部位/部件」命名，不要用「问题」命名 |
| `aliases` | 英文别名，买家实际会写的词 | **把各种写法都列上**：`hinge`/`hinges`/`spine`/`fold`/`crease` |
| `cat1` | 归属一级大类 | 决定它在统计里落在哪 |
| `modes` | 该部件**专属**的失效模式 | 通用模式请放 `global_modes`，见第 5 节 |

### 怎么找部件

跑 `discover.py` 拿候选，然后**逐个看证据句**判断：

```
候选部件      次数  现象数  共现现象
hinge         187    6      断裂:23, 覆盖不足:31, 无防护:52, ...
screen protector  142  5      顶膜:38, 气泡:29, ...
```

判断标准：
- **是**：能对应到实物上的一块（hinge/hinges/screen protector/stand/battery/zip）
- **不是**：描述状态的词（cheap/flimsy/broken）、泛指（case/product/thing）、
  评价维度（quality/color/size）

`discover.py` 已经过滤了大部分停用词，但**同义词与复合词**仍需你人工确认。

### 部件不一定是「零件」

- 耳机：耳塞、充电仓、电池、挂绳、按键
- 保温杯：杯盖、密封圈、内胆、吸管
- 衣服：拉链、袖口、标签、面料
- 家具：桌腿、抽屉滑轨、连接件、气压杆

也可以是**功能/属性维度**：`续航`、`充电速度`、`降噪`、`防水`。

---

## 3. failure_modes（失效模式）

失效模式 = 跨品类可复用的**问题形态**。这份库跨品类通用，
只有当新品类出现全新形态时才需要加。

```json
{
  "name": "撑不住",
  "desc": "支起后承不住重量，会倒下或角度自己变",
  "cat1": "结构/功能配件",
  "patterns": [
    "(does not|doesnt|won.t|cannot)[^.]{0,20}(hold|support|stand)[^.]{0,25}(weight|phone|upright|up)",
    "not strong enough to hold",
    "phone won.t stand"
  ]
}
```

**写正则的要点**：

| 技巧 | 例子 |
|---|---|
| `[^.]{0,20}` 跨词 | `(does not)[^.]{0,20}(fit)` |
| 缩写要都写 | `does not\|doesnt\|did not\|didnt\|won't\|wont` |
| 词边界 | `(?<![a-z])hinge(?![a-z])` 防误命中 |
| 允许变体 | `crack\|cracked\|cracking` |

**顺序重要**：引擎按数组顺序匹配，先命中先归属。
把**更具体的**放前面（`顶膜` 放 `气泡` 前面），泛化的放后面。

---

## 4. 一级大类（9 类固定）

```
Listing预期不符  结构/功能配件  产品做工&材质  尺寸贴合
外观手感  包装物流  使用体验  性价比  其他
```

跨品类通用，不需要改。要改的话改 `failure_modes[].cat1` 和 `parts[].cat1`。

---

## 5. 模式与部件的配对：global_modes + parts[].modes

引擎按**两级**匹配失效模式：

```
第一轮：parts[].modes —— 该部件「专属」的模式（最具体，优先命中）
第二轮：global_modes    —— 通用模式，对所有部件生效
第三轮：failure_modes 全表兜底
```

### global_modes（通用模式）

像「断裂脱落」「不贴合」「做工粗糙」「防护不足」这类**几乎每个部件都可能出现**的模式，
放进 `failure_modes` 后，再在 `global_modes` 里声明名字即可：

```json
"global_modes": ["断裂脱落", "不贴合", "做工粗糙", "防护不足", "完全失效"]
```

这样**不用在每个部件重复声明**，配置量能减一半以上。

### parts[].modes（部件专属模式）

只写**该部件特有**的模式，避免误配：

```json
{
  "name": "磁吸环",
  "aliases": ["magsafe", "mag safe", "magnetic ring", "磁吸环"],
  "cat1": "结构/功能配件",
  "modes": ["磁吸失效", "对位偏差", "结构干扰"]
}
```

| 场景 | 放哪 |
|---|---|
| 「断裂」——任何部件都可能断 | `failure_modes` + `global_modes` |
| 「磁吸失效」——只有磁吸环会这样 | `failure_modes` + 该部件的 `modes` |
| 「气泡」——只有贴膜会有 | `failure_modes` + 该部件的 `modes` |

> **注意**：`parts[].modes` / `global_modes` 里写的模式名必须与 `failure_modes[].name`
> **完全一致**，否则静默失效。用 `validate_taxonomy.py` 查。

---

## 6. extra_translations

品类专属英文词补翻译：

```json
"extra_translations": {
  "magsafe": "MagSafe",
  "hinge protector": "铰链护盖",
  "kickstand": "支架"
}
```

---

## 7. 调参循环

```
discover.py 拿候选
   ↓
写 parts / failure_modes / global_modes
   ↓
validate_taxonomy.py 自检（30 秒，先跑这个）
   ↓
run.py --audit 看抽样
   ↓
归类不对 → 改 patterns 或补 aliases → 重跑
   ↓
未归类仍多 → 补 failure_modes 或 parts
```

**终止标准**：未归类占比 < 15%，且抽样的 60 条里没有明显的系统性错误。

---

## 8. 实战踩过的坑（写配置前先读）

### 坑 1：模式名与部件白名单对不上 → 规则全部失效

`parts[].modes` / `global_modes` 里写的模式名必须与 `failure_modes[].name`
**完全一致**。写错不会报错，只会**静默失效**（模式永远匹配不上）。

```bash
# 直接用自检脚本，别手写这段
python scripts/validate_taxonomy.py --config taxonomy.json
```

### 坑 2：缩写写法必须两种都覆盖

`normalize()` 会去掉撇号：`doesn't → doesnt`、`it's → its`。
所以配置里 **不能只写 `does not`**，必须同时写 `doesnt` / `doesn.?t`：

```json
"patterns": ["does not fit", "doesnt fit", "doesn.?t fit"]
```

（引擎已内置 `_fix_pattern` 自动把 `does not` → `doesnt`，但 `doesn.?t` 这种写法仍建议显式给出。）

### 坑 3：`case`/`cover`/`product` 是商品本体，不是评价词

把它们放进「正面词表」会导致 "Love the case" 被判成负面
（因为 `love` 命中了，但「带否定→负面」的分支逻辑写反时更糟）。

- 正面词表：只放 `love / like / great / recommend / happy` 这类**评价词**
- 商品本体名（case/cover/product）：只用于**部件识别**，不参与情感打分

### 坑 4：转折句的重点在后半

"It is good but not great" 的重点是后半。
引擎已内置 `TURN_SPLIT_RX` 取后半句判定，但配置里的模式也应覆盖后半句的表达
（`not great` / `but it fell off` / `but the ring broke`）。

### 坑 5：否定词 + 负面词 ≠ 负面

"won't be damaged"、"no problems" 是**好评**。
引擎已内置 `NEG_NEG_PAIR_RX` 处理这类消歧。

### 坑 6：长评要按句拆 + 部件继承

一条 500 字符的评论会拆成 5-10 个观点。英文常用代词指代部件
（"the hinge cover moves... **it** doesn't stick"），
引擎已内置**同原文内部件继承**（`last_part`）。

### 坑 7：说明页/元信息表要排除

卖家精灵等导出工具常带一个 `Note` 页（客服电话、插件说明）。
引擎按表名 + 单元格特征自动跳过，但也要确认运行日志里没有混入。

### 坑 8：两个模式共用同一条 patterns → 先声明的永远赢

比如「缺口配件」和「覆盖不全」都写了 `not included`，
引擎按 `failure_modes` 数组顺序匹配，**先声明的赢**，后声明的这条 patterns 形同虚设。
`validate_taxonomy.py` 会把这类重复报出来，要么合并模式，要么把正则写得更互斥。

### 坑 9：叙述句会被当成观点

"I've used some other cases with a hinge cover…"、"I came from an OtterBox Defender…"
是**背景交代**，不是对本品的评价。引擎已内置叙述句过滤
（`NARRATIVE_RX` / `OTHER_PRODUCT_RX`），但仍要用 `--audit` 抽查确认没有漏网的。

### 坑 10：长句不要用规则翻译

规则翻译只覆盖 ≤8 词的短评价句。长句逐词拼会产生大量中英混排，
比保留英文更糟。长句走 `--export-zh-todo` → Agent 翻 → `--zh` 回灌。

---

## 9. 自检清单（跑完必须过一遍）

- [ ] `validate_taxonomy.py` 无 ERROR（坑 1）
- [ ] 没有两个模式共用同一条 patterns（坑 8）
- [ ] 每个模式的 patterns 同时覆盖 `does not` / `doesnt` / `doesn.?t` 三种写法（坑 2）
- [ ] 正面词表里没有 case/cover/product（坑 3）
- [ ] 运行的日志里没有「判定为说明/元信息表」之外的异常表（坑 7）
- [ ] `--audit` 抽样里，5 星评论没有大面积被判负面（情感判定回归）
- [ ] `--audit` 抽样里没有「他人产品/购买背景」被当成观点（坑 9）
- [ ] 痛点排行里没有「未指明」这类兜底桶（已自动排除）
- [ ] `--strict` 质量门禁通过（或已知原因并说明）
