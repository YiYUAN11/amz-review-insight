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
  "modes": ["无防护", "覆盖不足", "宣传误导", "断裂"]
}
```

| 字段 | 作用 | 要点 |
|---|---|---|
| `name` | 中文名，同时用于在原文中直接匹配中文 | 用「部位/部件」命名，不要用「问题」命名 |
| `aliases` | 英文别名，买家实际会写的词 | **把各种写法都列上**：`hinge`/`hinges`/`spine`/`fold`/`crease` |
| `cat1` | 归属一级大类 | 决定它在统计里落在哪 |
| `modes` | 该部件**可能**出现的失效模式 | 留空 = 不限；填了可避免模式错配 |

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

## 5. 模式与部件的配对

`parts[].modes` 是白名单。举例：

- 「铰链」只可能是 `无防护/覆盖不足/宣传误导/断裂/形变`
- 「磁吸环」只可能是 `磁吸失效/对位偏差/结构干扰`

不写 `modes` 时，引擎会用**全局**模式表匹配——容易出现
「磁吸环 → 断裂」这种不合理配对。所以**建议每个部件都写 modes**。

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
写 parts / failure_modes
   ↓
run.py --audit 看抽样
   ↓
归类不对 → 改 patterns 或补 aliases → 重跑
   ↓
未归类仍多 → 补 failure_modes 或 parts
```

**终止标准**：未归类占比 < 15%，且抽样的 60 条里没有明显的系统性错误。
