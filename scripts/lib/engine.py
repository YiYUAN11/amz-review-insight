# -*- coding: utf-8 -*-
"""
通用电商评论洞察引擎 —— 配置驱动的多级标签体系

设计要点：
1. 标签体系不硬编码品类。品类知识全部来自 taxonomy 配置（parts / failure_modes）。
2. 发现阶段（discover）自动从语料挖掘部件候选，交给 Agent 判断后写进配置。
3. 一级大类 9 类固定跨品类通用；二级标签由「部件 × 失效大类」组合生成；
   三级细分来自 failure_modes 的具体失效模式。
"""
import io
import json
import os
import re
from collections import Counter, defaultdict

# ======================================================================
# 一级大类：跨品类固定
# ======================================================================
CAT1_ORDER = [
    'Listing预期不符',
    '结构/功能配件',
    '产品做工&材质',
    '尺寸贴合',
    '外观手感',
    '包装物流',
    '使用体验',
    '性价比',
    '其他',
]

# 平台下拉理由（Amazon 买家之声的标准选项）—— 无具体落点，单独成列
PLATFORM_REASONS = {
    'not as expected': '与描述预期不符（平台理由）',
    'changed mind': '改变主意（平台理由）',
    'change mind': '改变主意（平台理由）',
    'defective': '商品有缺陷（平台理由）',
    'damaged': '到货已破损（平台理由）',
    'received wrong item': '错发商品（平台理由）',
    'no longer needed': '不再需要（平台理由）',
    'bought by mistake': '买错了（平台理由）',
    'better price available': '别处有更低价（平台理由）',
    'item arrived too late': '到货太晚（平台理由）',
    'unauthorized purchase': '非本人下单（平台理由）',
    'better description': '描述需改进（平台理由）',
    'better images': '图片需改进（平台理由）',
    'quality': '质量不佳（平台理由）',
    'return': '退货（平台理由）',
    'other': '其他（平台理由）',
}

# 平台理由的归一化索引（惰性构建，避免依赖定义顺序）
_PLATFORM_KEYS_CACHE = None


def _platform_keys():
    global _PLATFORM_KEYS_CACHE
    if _PLATFORM_KEYS_CACHE is None:
        _PLATFORM_KEYS_CACHE = {norm_key(k): v for k, v in PLATFORM_REASONS.items()}
    return _PLATFORM_KEYS_CACHE


# 平台理由尾部允许出现的填充词（否则不视为纯平台项）
FILLER_TAIL = {
    '', 'now', 'at all', 'no', 'yes', 'n a', 'na', 'none', 'very', 'just',
    'so', 'too', 'really', 'totally', 'completely', 'here', 'thanks',
    'no thanks', 'not really', 'not at all', 'overall', 'in general',
    'item', 'product', 'quality', 'poorly', 'badly', 'return', 'returned',
    'case', 'unit', 'one', 'thing',
}


def match_platform(text):
    """识别平台下拉理由。只有尾部为填充词时才做前缀匹配，避免吞掉有效内容。"""
    n = norm_key(text)
    if not n:
        return None, False
    keys = _platform_keys()
    if n in keys:
        return keys[n], True
    for k, v in keys.items():
        if n.startswith(k):
            rest = n[len(k):].strip()
            if rest in FILLER_TAIL:
                return v, True
    return None, False


# 无信息量的占位回答
PLACEHOLDER = {
    'no', 'yes', 'na', 'n/a', 'none', 'nope', 'n', 'y', 'k', 'd', 'non', 'nah',
    'not sure', 'idk', 'unsure', 'hard to say', 'maybe', 'nothing', 'thanks',
    'the question was not relevant', 'i did not know how to answer',
    'i did not want to respond to questions', 'no more comments', 'that is all',
    'that is all', 'perfect', 'delivered promptly', 'delivery was good',
    'delivery was fine', 'never used it', 'just testing the feel',
}

# ======================================================================
# 通用拼写纠错（跨品类通用，只修明显错字）
# ======================================================================
TYPO_FIX = [
    (r"\bdon't\b", 'dont'), (r"\bdoesn't\b", 'doesnt'), (r"\bdidn't\b", 'didnt'),
    (r"\bwon't\b", 'wont'), (r"\bcan't\b", 'cant'), (r"\bcouldn't\b", 'couldnt'),
    (r"\bit's\b", 'its'), (r"\bthat's\b", 'that is'), (r"\bi'm\b", 'i am'),
    (r"\bi've\b", 'i have'), (r"\bthey're\b", 'they are'), (r"\bwasn't\b", 'wasnt'),
    (r"\bisn't\b", 'isnt'), (r"\bwouldn't\b", 'wouldnt'), (r"\bshouldn't\b", 'shouldnt'),
    (r"\bflinsy\b", 'flimsy'), (r"\bjanky\b", 'cheap'), (r"\bquality\s*issue\b", 'quality'),
]


def normalize(text):
    """小写 + 去撇号 + 修错字 + 压缩空白"""
    if not text:
        return ''
    s = text.replace("'", '').replace('\u2019', '')
    s = s.replace('\u2022', ' ').replace('\u00b7', ' ').replace('\u2013', '-')
    s = re.sub(r'\s+', ' ', s).strip().lower()
    for a, b in TYPO_FIX:
        s = re.sub(a, b, s)
    return s


def norm_key(text):
    """用于比对的口径：仅保留字母数字与空格"""
    s = normalize(text)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


# ======================================================================
# 配置
# ======================================================================
# 缩写正则的兼容改写：
# normalize() 会去掉撇号（isn't -> isnt），而配置里的模式常写成 isn.t，
# 这里统一改成 isn.?t，两种写法都能命中。
_CONTRACTION_FIX = [
    (r'\b(is|was|are|were|do|does|did|has|have|had|could|would|should|'
     r'must|need|ai)n\.t\b', r'\1n.?t'),
    (r'\b(won|can|shan)\.t\b', r'\1.?t'),
    (r"\bdon\.t\b", r'don.?t'),
]


def _fix_pattern(pat):
    """
    改写配置里的缩写正则，使其能匹配 normalize() 之后的文本。
    normalize() 会把撇号去掉：doesn't -> doesnt，it's -> its。
    因此配置里写的 (does not|doesnt|doesn.t) 必须统一成 doesnt 可匹配的形式。
    """
    out = pat
    for a, b in _CONTRACTION_FIX:
        out = re.sub(a, b, out)
    # 关键：把 'does not' / 'doesnt' / 'doesn.t' 三种写法统一成 'doesnt'
    # （normalize 已去撇号，故只需处理带空格与带点的写法）
    out = re.sub(r'\bdoes\s+not\b', 'doesnt', out)
    out = re.sub(r'\bdid\s+not\b', 'didnt', out)
    out = re.sub(r'\bwill\s+not\b', 'wont', out)
    out = re.sub(r'\bwould\s+not\b', 'wouldnt', out)
    out = re.sub(r'\bcould\s+not\b', 'couldnt', out)
    out = re.sub(r'\bshould\s+not\b', 'shouldnt', out)
    out = re.sub(r'\bis\s+not\b', 'isnt', out)
    out = re.sub(r'\bare\s+not\b', 'arent', out)
    out = re.sub(r'\bwas\s+not\b', 'wasnt', out)
    out = re.sub(r'\bwere\s+not\b', 'werent', out)
    out = re.sub(r'\bhas\s+not\b', 'hasnt', out)
    out = re.sub(r'\bhave\s+not\b', 'havent', out)
    out = re.sub(r'\bhad\s+not\b', 'hadnt', out)
    out = re.sub(r'\bcan\s+not\b', 'cant', out)
    out = re.sub(r"\bdon'?t\b", 'dont', out)
    out = re.sub(r'\bdoesn\.t\b', 'doesnt', out)
    out = re.sub(r'\bdidn\.t\b', 'didnt', out)
    out = re.sub(r'\bwon\.t\b', 'wont', out)
    out = re.sub(r'\bcan\.t\b', 'cant', out)
    out = re.sub(r'\bcouldn\.t\b', 'couldnt', out)
    out = re.sub(r'\bshouldn\.t\b', 'shouldnt', out)
    out = re.sub(r'\bisn\.t\b', 'isnt', out)
    out = re.sub(r'\bwasn\.t\b', 'wasnt', out)
    out = re.sub(r'\bweren\.t\b', 'werent', out)
    out = re.sub(r'\bit\'s\b', 'its', out)
    out = re.sub(r"\bthat's\b", 'that is', out)
    out = re.sub(r"\bi'm\b", 'i am', out)
    out = re.sub(r"\bi've\b", 'i have', out)
    out = re.sub(r"\bthey're\b", 'they are', out)
    return out


class Taxonomy:
    """标签体系配置"""

    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.parts = cfg.get('parts', [])
        self.modes = cfg.get('failure_modes', [])
        self.cat1_of_part = {}
        for p in self.parts:
            self.cat1_of_part[p['name']] = p.get('cat1', '结构/功能配件')
        self.part_alias = {}
        for p in self.parts:
            for a in p.get('aliases', []):
                self.part_alias[normalize(a)] = p['name']
        # 部件 → 该部件**专属**的失效模式（通用模式由 global_modes 提供）
        self.part_modes = {p['name']: p.get('modes', []) for p in self.parts}
        # 全局通用模式：对所有部件生效，不必在每个部件重复声明
        self.global_modes = list(cfg.get('global_modes', []))
        # 失效模式表
        self.mode_list = []
        for m in self.modes:
            self.mode_list.append({
                'name': m['name'],
                'desc': m.get('desc', ''),
                'cat1': m.get('cat1', '结构/功能配件'),
                'rx': [re.compile(_fix_pattern(p), re.I) for p in m.get('patterns', [])],
            })
        self.extra_tr = cfg.get('extra_translations', {})

    def detect_part(self, text):
        """
        识别文本说的是哪个部件。
        顺序：中文名 → 英文别名（含多词组）→ 别名的词干匹配
        """
        low = normalize(text)
        # 1) 中文部件名直接出现
        for p in self.parts:
            if p['name'] and p['name'] in text:
                return p['name']
        # 2) 英文别名：多词优先，避免 "cover" 抢在 "hinge cover" 前面
        aliases = sorted(self.part_alias.items(), key=lambda x: -len(x[0]))
        for a, name in aliases:
            if not a:
                continue
            if re.search(r'(?<![a-z])' + re.escape(a) + r'(?![a-z])', low):
                return name
        return None

    def detect_part_loose(self, text):
        """
        宽松匹配：别名去掉限定词后仍能命中（如 "the hinge cover" → "hinge cover" → "hinge"）。
        用于长句中部件词被修饰语隔开的情况。
        """
        part = self.detect_part(text)
        if part:
            return part
        low = normalize(text)
        for p in self.parts:
            for a in p.get('aliases', []):
                core = re.sub(r'^(the|a|an|its|their|my|your|his|her)\s+', '', normalize(a))
                if len(core) >= 4 and re.search(r'(?<![a-z])' + re.escape(core) + r'(?![a-z])', low):
                    return p['name']
        return None

    def classify_mode(self, text, part=None):
        """
        识别失效模式 → (模式名, 现象描述)

        匹配顺序（设计要点）：
          1) 该部件**专属**模式（parts[].modes 里声明的）优先 —— 避免通用模式抢走
          2) 全局模式表（failure_modes）—— 通用模式对所有部件生效
        这样配置里只需给部件写「它特有的模式」，通用模式不必在每个部件重复声明。
        """
        low = normalize(text)
        # 第一轮：部件专属模式（最具体，优先）
        if part and self.part_modes.get(part):
            for m in self.mode_list:
                if m['name'] not in self.part_modes[part]:
                    continue
                for rx in m['rx']:
                    if rx.search(low):
                        return m['name'], m['desc']
        # 第二轮：全局通用模式
        if self.global_modes:
            for m in self.mode_list:
                if m['name'] not in self.global_modes:
                    continue
                for rx in m['rx']:
                    if rx.search(low):
                        return m['name'], m['desc']
        # 第三轮：全表兜底
        for m in self.mode_list:
            for rx in m['rx']:
                if rx.search(low):
                    return m['name'], m['desc']
        return None, None


# ======================================================================
# 文本拆分
# ======================================================================
SPLIT_PAT = re.compile(
    r'\s*\|\s*'
    r'|(?<=[a-z\)])\.\s+'
    r'|;\s*'
    r'|\s+but\s+'
    r'|\s+plus\s+'
    r'|\s+also\s+'
    r'|\s+and\s+(?=(?:the |it |they |this |no |not |does |did |will |there |'
    r'[a-z]+ (is|was|are|were|does|did|has|have|will) )\b)'
    r'|\s*,\s*(?=(?:but |plus |also )?(?:the |it |they |no |not |does |did |too |very |there )\b)'
)

MIN_WORDS = 3


def split_parts(text):
    """第一层：按 | 拆成字段片段"""
    return [p.strip() for p in re.split(r'\s*\|\s*', text) if p.strip()]


# 悬空片段结尾：这些词结尾说明句子没说完，应与下一段合并
# 例："The screen protector was" + "very difficult to install" → 一句完整抱怨
DANGLING_TAIL_RX = re.compile(
    r"\b(is|was|are|were|be|been|being|has|have|had|does|did|do|will|would|"
    r"can|could|should|must|might|may|very|really|quite|too|so|a|an|the|to|"
    r"and|or|but|that|which|who|when|while|with|for|of|in|on|at|by|from|"
    r"as|it|its|my|your|their|our|this|these|those|some|more|less|"
    r"only|just|even|not|no|not quite)\s*$", re.I)

# 尾巴上挂着的转折/顺承标记：应移到下一段开头（保留转折语义）
TRAIL_DISCOURSE_RX = re.compile(
    r"\s+(however|but|so|also|though|although|yet|meanwhile|instead|"
    r"otherwise|plus|then|and|or)\s*$", re.I)

# 句子开头的话语标记：切分时保留在下一段
LEAD_DISCOURSE_RX = re.compile(
    r"^(however|but|so|also|though|although|yet|meanwhile|instead|"
    r"otherwise|plus|then|and|or)\b[\s,]*", re.I)


def _merge_dangling(chunks):
    """把没说完的悬空片段与后续片段合并"""
    out = []
    for c in chunks:
        if out and DANGLING_TAIL_RX.search(out[-1]) and \
                len(out[-1].split()) <= 8:
            out[-1] = (out[-1] + ' ' + c).strip()
        else:
            out.append(c)
    return out


def _fix_discourse(chunks):
    """把挂在段尾的话语标记移到下一段开头"""
    out = list(chunks)
    for i in range(len(out) - 1):
        m = TRAIL_DISCOURSE_RX.search(out[i])
        if m:
            word = m.group(1)
            out[i] = out[i][:m.start()].strip()
            out[i + 1] = (word + ' ' + out[i + 1]).strip()
    return [c for c in out if c.strip()]


def split_clauses(part):
    """第二层：把一段自由文本拆成最小独立感受"""
    parts = [p.strip() for p in SPLIT_PAT.split(part) if p and p.strip()]
    out = []
    for p in parts:
        if out and len(p.split()) < MIN_WORDS:
            out[-1] = (out[-1] + ' ' + p).strip()
        else:
            out.append(p)
    merged = []
    for p in out:
        if merged and len(p.split()) < MIN_WORDS:
            merged[-1] = (merged[-1] + ' ' + p).strip()
        else:
            merged.append(p)
    merged = _merge_dangling(merged)
    merged = _fix_discourse(merged)
    # 清理重复与尾随连接词
    seen, cleaned = set(), []
    for p in merged:
        p = re.sub(r'\s+(and|but|plus|also|or)$', '', p).strip(' .,;:-')
        k = norm_key(p)
        if len(p) < 2 or k in seen:
            continue
        seen.add(k)
        cleaned.append(p)
    return cleaned


def is_placeholder(s):
    k = norm_key(s)
    return (not k) or k in PLACEHOLDER or len(k) <= 1


# ======================================================================
# 情感与具象点判定
# ======================================================================
POSITIVE_RX = re.compile(
    r'\b(love|love it|loved|like|liked|happy|pleased|great|good|nice|perfect|'
    r'excellent|amazing|awesome|recommend|impressed|solid|well made|works well|'
    r'works great|fits well|fits nicely|fits perfectly|perfect fit|no complaints|'
    r'worth it|protective|durable|great price|good price|decent price|happy with|'
    r'works with|it clips in and stays|it just works)\b', re.I)

# 负面信号：明确的问题描述（不含 not/no 这类否定词时也命中）
NEGATIVE_RX = re.compile(
    r'\b(broke|broken|snapped|cracked|crack|flimsy|fragile|cheap|cheaply|weak|'
    r'loose|wobbly|wobble\w*|unstable|defective|damaged|scratch\w*|tore|torn|split|'
    r'slippery|rough|sharp|bulky|poorly|badly|shabby|janky|warped|bent|'
    r'deformed|dent\w*|leak\w*|corroded|rusted|yellow\w*|fade\w*|peel\w*|'
    r'bubbles|bubble up|popping up|lift\w* up|too thin|too thick|'
    r'too big|too small|too soft|too heavy|too light|too loose|too early|too late|'
    r'\bbad\b|\bworse\b|\bworst\b|\bjunk\b|\bgarbage\b|\btrash\b|\bterrible\b|'
    r'\bhorrible\b|\bawful\b|\buseless\b|\bworthless\b|\bpointless\b|'
    r'\bdusty\b|\bdirty\b|\bcheapness\b|\boverpriced\b|\bnot worth\b|'
    # 双词质量表述
    r'poor quality|low quality|bad quality|cheap quality|terrible quality|'
    r'horrible quality|quality issue|quality concern|not good|not great|'
    r'not satisfied|not impressed|disappoint\w*|waste of|'
    r'doesn.?t fit|does not fit|didn.?t fit|did not fit|not fit|'
    r'doesn.?t work|does not work|not work|stopped working|'
    r'wrong color|wrong size|wrong model|wrong item|'
    r'can.?t (use|open|close|hold|charge)|couldn.?t|'
    r'no (hinge|protection|cover|part)|missing|not included|'
    r'not compatible|incompatible|falls? off|comes? off|came off|pops? off|'
    r'comes? apart|fell apart|comes? loose|not stay|not secure|not stable|'
    r'(fell|falls|falling|fell off|fell out|popped off|blew off|tears? off|torn off)|'
    r'(broke off|ripped off|ripped|detached|popped loose|worked loose|came undone)|'
    r'came apart|flapped|loosened|worked its way loose|slipped off|'
    r'not strong|not sturdy|not durable|not comfortable|not smooth|not flush|'
    r'not worth|not happy|not pleased|not what i expected|not good|not great|'
    r'don.?t (like|buy|recommend|waste)|wouldn.?t (recommend|buy)|'
    r'doesn.?t (work|fit|protect)|no protection|only (protects|the back)|'
    r'not (a )?full case|incomplete|scam|rip off|overpriced|'
    r'could be (better|improved)|needs? (to be|improvement|a better)|'
    r'flaw\w*|issue\w* with|problem\w* with|'
    r'unflattering|unforgivable|horrid|not good|not impressed|'
    r'badly flawed|poorly designed|flawed design|'
    r'never leveled|not leveled|does not level|'
    r'charging port[^.]{0,30}(on the bottom|bottom of)|'
    r'difficult to install|hard to install|'
    r'less destructive|better options|save your money|'
    r'do not install|do not buy|skip this one|'
    r'sending this back|will be sending back|'
    r'will last|how long will|not real durable|'
    r'does not seem to align|not align 100|'
    r'not magnetic|spring loaded|'
    r'not the best design|best design|'
    r'hold up the phone|holding up the phone|'
    r'not stable|unstable|won.t stand|does not stand|'
    r'adds too much|too much weight|too much bulk|'
    r'never use it again|removing it|removed the front|'
    r'could be a four|fix the stand|'
    r'clearance of the front|display setting|'
    r'outer display|inner display|'
    r'volume|button controls|controls work|'
    r'not as good|not good quality)\b',
    re.I)

# 否定词（把中性/正面翻转为负面）
# 注意：without 常用于"不碍事/不影响"的好评，单独排除
NEGATOR_RX = re.compile(
    r"\b(not|no|never|doesn'?t|does not|didn'?t|did not|won'?t|will not|wont|"
    r"cannot|can'?t|cant|couldn'?t|could not|shouldn'?t|hardly|"
    r"neither|nor|nothing|nobody|isn'?t|is not|aren'?t|are not|wasn'?t|was not|"
    r"weren'?t|were not|hasn'?t|has not|haven'?t|have not|hadn'?t|had not|"
    r"don'?t|dont|doesnt|didnt|wouldn'?t|would not|ain'?t|isnt|wasnt|werent|"
    r"didn|doesn|won|didnt|cant|couldnt|shouldnt|isnt|wasnt|werent)\b", re.I)

# 明确的正面表述（优先级最高）
STRONG_POS_RX = re.compile(
    r'\b(i love|love it|loved it|very good|great case|nice case|perfect|'
    r'excellent|awesome|beyond what i expected|i am happy|very happy|'
    r'no complaints|highly recommend|works great|works well|'
    r'fits perfectly|great price|good price|decent price|worth it|'
    r'protective|very solid|worth every penny|top tier|'
    r'delivers amazing quality|amazing quality|great value|'
    r'without getting in the way|in the way\b|'
    r'exceptionally easy|very easy|easy to (use|install|apply)|'
    r'meshes very well|very well|really (like|love|enjoy)|'
    r'glides smoothly|opens and closes smoothly|moves with the phone|'
    r'feels premium|premium quality|highly recommend|'
    r'superior|superb|wonderful|fantastic|impressed|'
    r'thoughtful (design|combination)|clean (design|look)|'
    r'no issues|zero issues|no complaints|would buy again|buy again|'
    r'glad i (bought|got)|best case|best (purchase|buy)|'
    r'solid (case|product)|feels great|looks great|'
    # ---- 审计补充：常见好评表达 ----
    r'feels (ok|okay|fine|good|great)|feels really|'
    r'works? flawlessly|work[s]? (well|perfectly|flawlessly)|'
    r'game ?changer|everything fits|fits correctly|no loose parts|'
    r'perfect size|everything (fits|works)|not (too much|much) (weight|bulk)|'
    r'worthwhile|thoughtful|maintains a secure|secure grip|'
    r'no adhesive (strips|needed)|doesn.?t have any adhesive|'
    r'good thing|pleased with|happy with|more impressed|'
    r'i love that|i love how|love the|really like (it|this|these)|'
    r'exactly (as|what)|as (described|advertised|pictured)|'
    r'easy to install|easy to (use|remove|put)|simple to|'
    r'no complaints|zero complaints|nothing wrong|no issues|'
    r'study|sturdy|well made|well built|properly (fits|installed)|'
    r'does not (interfere|peel)|doesn.?t (interfere|peel|shrink)|'
    r'glides smoothly|smoothly|works properly|'
    r'not impressed|too impressed|'
    r'would (buy|get) again|buy again|'
    r'but the stand is not good|'
    r'good (value|quality|price)|'
    r'highly recommend|definitely recommend|would recommend|'
    r'glad|pleased|satisfied|'
    r'works (well|great|perfectly|flawlessly)|'
    r'looks (good|great|nice|perfect)|'
    r'feels (good|great|perfect|solid|amazing)|'
    r'pretty good|quite good|really good|very good|'
    r'no (complaints|problems|issues)|'
    r'sounds good|happy|pleased|'
    r'(love|likes|loved|like) (the |this |that )?(case|cases|cover|product)|'
    r'(recommend|recommended) (this |the |it )?(case|product)|'
    r'(good|great|nice|excellent) (case|product|quality)|'
    r'case is (great|good|nice|perfect|excellent)|'
    r'(would|will) (definitely |highly )?recommend)\b', re.I)

# 具象点：出现具体部件/参数/动作/部位
CONCRETE_RX = re.compile(
    r'\b(broke|broken|snapped|cracked|crack|flimsy|loose|spin|rotat|hold|support|fit|'
    r'bubble|lift|charge|magnet|hinge|stand|ring|corner|frame|edge|cover|screen|'
    r'phone|device|protector|hinges|spine|warp|bent|click|noise|slip|collapse|'
    r'drop|pocket|install|open|close|switch|button|port|zip|strap|material|plastic|'
    r'metal|size|weight|inch|cm|mm|hour|day|week|month|year)\b', re.I)

DANGLING_RX = re.compile(
    r'^(it|this|that|they|the \w+|he|she)\s+'
    r'(does not|doesnt|is not|isnt|was not|wasnt|did not|didnt|will not|wont|cannot|cant)\b[\s\w]{0,12}$',
    re.I)


# 否定词后紧跟正面词 → 其实是好评（no issues / no brainer / not any of that）
NEG_POS_PAIR_RX = re.compile(
    r"\b(no|not|without|never|none)\s+"
    r"(issues?|problem\w*|complaint\w*|worries|concerns?|"
    r"brainer|regret\w*|complain\w*|issue|trouble|difficulty|"
    r"reservations?|objection\w*|qualif\w+|"
    r"way (to|of) (getting|it))\b", re.I)


# 否定词 + 负面词 → 实为正面（won't be damaged / no problems / not broken）
NEG_NEG_PAIR_RX = re.compile(
    r"\b(won'?t|wont|will not|wouldn'?t|would not|never|didn'?t|did not|doesn'?t|"
    r"does not|not|no)\s+"
    r"(be\s+|been\s+|being\s+|get\s+|got\s+)?"
    r"(damaged|broken|cracked|snapped|torn|scratched|worn|deformed|"
    r"disappointed|complain\w*|problem\w*|issue\w*|trouble|"
    r"bad|worse|worst|junk|useless|defective|faulty|"
    r"overpriced|disappoint\w*|regret\w*|hate|annoy\w*|"
    r"go\w*\s+wrong|fall\w*\s+apart)\b", re.I)


# 转折句：取 but/however/though 之后的半句（重点通常在后半）
TURN_SPLIT_RX = re.compile(
    r'\b(but|however|though|although|yet|unfortunately)\b', re.I)


def _focus_clause(text):
    """取转折后半句作为判定重点；无转折或后半过短则返回原文"""
    m = TURN_SPLIT_RX.search(text)
    if m and m.start() > 0:
        tail = text[m.end():].strip(' ,.;:!?')
        if len(tail.split()) >= 2:
            return tail
    return text


# 强正向短语：即使含否定词也判正向
# （"no loose parts"、"can't think of a single flaw"、"doesn't have any adhesive"…）
STRONG_POS_PHRASE_RX = re.compile(
    r"\b(no loose parts?|no (issues?|problems?|complaints?)|"
    r"can'?t think of a single flaw|not a single flaw|"
    r"doesn'?t have any adhesive|no adhesive|"
    r"makes .{0,30}(much )?easier|"
    r"game ?changer|"
    r"i love that|i love how|"
    r"thoughtful|"
    r"works? flawlessly|(?<!not )work[s]? (perfectly|flawlessly)|"
    r"everything fits|fits correctly|"
    r"no need to (shrink|adjust)|"
    r"without (getting in the way|interfering)|"
    r"doesn'?t (peel|interfere|shrink)|"
    r"snapped? on (cleanly|easily)|snaps? (on|around|in place) (cleanly|easily)|"
    r"doesn.?t do any of that|does not do any of that|"
    r"no complaints|zero complaints|nothing wrong)\b",
    re.I)


# ======================================================================
# 叙述句 / 背景句识别
# ======================================================================
# 纯叙述：描述使用经历、购买背景、他人产品对比，本身不含对本品的主观评价。
# 例："I've used some other cases with a hinge cover"、
#     "I came from an OtterBox Defender that ruined my screen protector"
# 这类句子若计入观点，会稀释真实痛点、污染统计口径。
# 注意：normalize() 会去掉撇号（i've → ive、you're → youre），
# 因此这里的正则必须同时兼容带撇号与不带撇号两种写法。
NARRATIVE_RX = re.compile(
    r"\b("
    r"i(?:ve| have| have)?(?: been)? (?:using|used|tried|tried out|tested|owned)"
    r"|i (?:have|had) (?:tried|used|owned|tested) (?:out )?\d+"
    r"|i came from|i come from|i switched (?:from|to)"
    r"|all of them being|of all of them"
    r"|on (?:work|home|weekend|travel|vacation)[\w-]* days?"
    r"|my (?:old|previous|prior|first|second|third|other) "
    r"(?:case|cases|phone|phones|cover|covers)"
    r"|since (?:then|last year|i bought|i got)"
    r"|if you(?:re| are) (?:on the fence|looking|interested|in the market|"
    r"in the market for)"
    r"|this is my first"
    r"|what i(?:ve| have) (?:been )?(?:looking|tried|wanted)"
    r")\b",
    re.I)

# 从属/条件状语句：交代场景，本身不含评价
# 例："So when on a FaceTime call or using the camera..."
SUBORDINATE_RX = re.compile(
    r"^(?:so|and|plus|also|then|but)?\s*"
    r"(?:when|while|whenever|unless|until)\b",
    re.I)

# 他人产品：句子指向的不是本品（对比、换机、前代产品）
OTHER_PRODUCT_RX = re.compile(
    r"\b(other (?:cases?|products?|brands?|manufacturers?|options?|phones?)|"
    r"some other|another (?:case|brand|company|one)|"
    r"previous iphones?|last phone|my old phone|"
    r"competitors?|third-party|"
    r"i came from|i come from|came from an? |"
    r"all of them being|of all of them|"
    r"otterbox|unicorn beetle|supcase|spigen|caseology)\b",
    re.I)

# 本品自指：句子明确指向本产品
SELF_REF_RX = re.compile(
    r"\b(this (?:case|cases|product|one|cover|screen protector|stand|ring|hinge|"
    r"front cover|back cover|design|screen protector)|"
    r"the (?:case|cases|product|cover|screen protector|stand|kickstand|"
    r"kick stand|ring|hinge cover|front cover|back cover|front part|back part|"
    r"screen|screen protector)|it|its|this|these)\b",
    re.I)


def _has_evaluation(text):
    """句子里是否存在主观评价信号（正面/负面/否定）"""
    low = normalize(text)
    return bool(
        STRONG_POS_RX.search(low) or POSITIVE_RX.search(low)
        or NEGATIVE_RX.search(low) or NEGATOR_RX.search(low)
        or STRONG_POS_PHRASE_RX.search(low))


def _has_self_ref(text):
    low = normalize(text)
    return bool(SELF_REF_RX.search(low))


def _is_narrative(text):
    """是否纯叙述句（背景交代，非观点）"""
    low = normalize(text)
    return bool(NARRATIVE_RX.search(low))


def _is_other_product(text):
    low = normalize(text)
    return bool(OTHER_PRODUCT_RX.search(low))


def is_narrative_clause(text, other_ctx=False):
    """
    是否为「叙述/背景句」——描述购买经历、使用背景或他人产品，
    本身不构成对本品的主观评价，计入观点会稀释真实痛点。

    other_ctx=True 表示承接了上文「他人产品」语境，
    此时只要没有明确指向本品，就视为叙述句（即使含负面词）。
    """
    low = normalize(text)
    if other_ctx:
        # 明确指向本品 → 回到本品语境，不排除
        if _has_self_ref(low):
            return False
        return True
    if _has_evaluation(low):
        return False
    # 从属状语句且不含部件名词 → 场景交代，非观点
    if SUBORDINATE_RX.match(low) and not CONCRETE_RX.search(low):
        return True
    return bool(NARRATIVE_RX.search(low) or OTHER_PRODUCT_RX.search(low))


# 轻微问题限定语：买家主动说明「不算大问题」，不应计入硬负面
# 例："It is not a major problem"、"not a deal breaker"、"only a minor issue"
MINOR_ISSUE_RX = re.compile(
    r"\b("
    r"not a major (?:problem|issue|concern|dealbreaker|deal breaker)"
    r"|not a deal ?breaker"
    r"|not a big (?:problem|issue|deal|dealbreaker)"
    r"|only a minor (?:issue|problem|complaint|nitpick|downside|drawback)"
    r"|minor (?:issue|problem|complaint|nitpick|downside|drawback)"
    r"|small (?:issue|problem|complaint|nitpick)"
    r"|just a minor"
    r"|nothin(g)? major"
    r"|barely noticeable"
    r"|not worth mentioning"
    r"|give me a little loss pause"
    r")\b",
    re.I)


def judge_sentiment(text, star=None):
    """
    判定情感。
    顺序：转折取后半 → 明确正面 → 否定+正面消歧 → 否定+负面消歧
          → 明确负面 → 否定词 → 正面词 → 星级 → 中性
    """
    low = normalize(text)
    focus = normalize(_focus_clause(text))
    has_turn = focus != low

    # 0) 强正向短语优先（即使含否定词）
    if STRONG_POS_PHRASE_RX.search(low) and not has_turn:
        return '正向'
    if has_turn and STRONG_POS_PHRASE_RX.search(focus):
        return '正向'

    def _has(rx, seg):
        return bool(rx.search(seg))

    def _negator(seg):
        return _has(NEGATOR_RX, seg)

    # 转折句：后半句是重点，若后半句有明确负面信号则优先判定
    if has_turn:
        if _has(NEGATIVE_RX, focus) or _negator(focus):
            return '负面'
        if _has(STRONG_POS_RX, focus) and not _negator(focus):
            return '正向'

    # 1) 明确正面（原文或转折后半）
    if (_has(STRONG_POS_RX, low) and not _negator(low)) or \
       (_has(STRONG_POS_RX, focus) and not _negator(focus)):
        return '正向'

    # 2) 否定词 + 正面词 → 实为好评（"no issues at all"、"a no brainer"）
    if _has(NEG_POS_PAIR_RX, low) or _has(NEG_POS_PAIR_RX, focus):
        return '正向'

    # 3) 否定词 + 负面词 → 实为好评（"won't be damaged"、"no problems"）
    if _has(NEG_NEG_PAIR_RX, low) or _has(NEG_NEG_PAIR_RX, focus):
        return '正向'

    # 3.5) 轻微问题限定语 → 中性（买家明说「不算大问题」）
    #      有转折时只看后半句：前半句的「不算大问题」不能盖住后半句的硬伤
    #      仅当句中没有其它硬负面信号时降级
    _minor_seg = focus if has_turn else low
    if _has(MINOR_ISSUE_RX, _minor_seg):
        hard = NEGATIVE_RX.search(low) or NEGATIVE_RX.search(focus)
        if not hard:
            return '中性'

    # 4) 明确负面信号（broken/flimsy/low quality…）
    if _has(NEGATIVE_RX, low) or _has(NEGATIVE_RX, focus):
        return '负面'

    # 5) 否定词 → 负面
    if _negator(low) or _negator(focus):
        return '负面'

    # 6) 正面词：带否定则负面（"not good"），否则正向（"Love the case"）
    if _has(POSITIVE_RX, low) or _has(POSITIVE_RX, focus):
        if _negator(low) or _negator(focus):
            return '负面'
        return '正向'

    # 7) 星级参考（评论表）
    if star is not None:
        if star >= 4:
            return '正向'
        if star <= 2:
            return '负面'
        return '中性'

    return '中性'

def judge_concrete(text, parts):
    """是否有明确具象点：提到具体部件或具体现象"""
    low = normalize(text)
    if CONCRETE_RX.search(low):
        return True
    for p in parts:
        if p.get('name') and normalize(p['name']) and normalize(p['name']) in low:
            return True
    # 短句且无具体词 → 无具象点
    if len(low.split()) <= 3 and not re.search(
            r'\b(not|no|very|too|so|just|really|quite|not great|not good)\b', low):
        return False
    return bool(re.search(
        r'\b(not|no|very|too|so|just|really|quite|not great|not good|bad|poor|'
        r'cheap|flimsy|wrong|missing)\b', low))


# ======================================================================
# 观点拆分主流程
# ======================================================================
def split_opinions(rows, tax, source_name):
    """
    rows: [{ 'text': 原始反馈文本, 'star': 星级或None, ... }]
    返回观点列表
    """
    ops = []
    for row in rows:
        text = (row.get('text') or '').strip()
        if not text:
            continue
        # 每行自带来源；缺省才回落到参数
        row_src = row.get('src') or source_name
        seen = set()
        last_part = None
        other_ctx = False
        for part in split_parts(text):
            n = norm_key(part)
            # 平台下拉理由：整段即一项
            pname, is_pure = match_platform(part)
            if pname:
                if n in seen:
                    continue
                seen.add(n)
                emo = ('中性' if ('改变主意' in pname or '不再需要' in pname
                                  or '买错' in pname or '非本人' in pname)
                                  else '负面')
                ops.append(dict(
                    src=row_src, raw=text, snippet=part,
                    sentiment=emo,
                    cat1='Listing预期不符' if '预期不符' in pname else '其他',
                    cat2=pname, cat3='', platform=True, concrete=False,
                    doubt=False, star=row.get('star'),
                ))
                continue
            if is_placeholder(part):
                continue
            # 自由文本：继续细拆
            for cl in split_clauses(part):
                cn = norm_key(cl)
                if not cn or cn in seen or is_placeholder(cl):
                    continue
                # 子句也可能只是平台理由（长句里拆出来的）
                pname2, _ = match_platform(cl)
                if pname2:
                    seen.add(cn)
                    emo2 = ('中性' if ('改变主意' in pname2 or '不再需要' in pname2
                                       or '买错' in pname2 or '非本人' in pname2)
                                       else '负面')
                    ops.append(dict(
                        src=row_src, raw=text, snippet=cl, sentiment=emo2,
                        cat1='Listing预期不符' if '预期不符' in pname2 else '其他',
                        cat2=pname2, cat3='', platform=True, concrete=False,
                        doubt=False, star=row.get('star'),
                    ))
                    continue
                seen.add(cn)
                # ---- 叙述/背景句过滤：不计入观点 ----
                if is_narrative_clause(cl, other_ctx):
                    # 语境传递：指向他人产品 → 后续无主语指向的短句仍属他人语境
                    if _is_other_product(cl) and not _has_self_ref(cl):
                        other_ctx = True
                    elif _has_self_ref(cl):
                        other_ctx = False
                    continue
                if _has_self_ref(cl):
                    other_ctx = False
                part_name = tax.detect_part(cl) or tax.detect_part_loose(cl)
                # 同一原文内继承上文部件（英文常用代词指代部件）
                if not part_name and last_part:
                    part_name = last_part
                if part_name:
                    last_part = part_name
                sent = judge_sentiment(cl, row.get('star'))
                concrete = judge_concrete(cl, tax.parts)
                mode, desc = tax.classify_mode(cl, part_name)

                # 正向观点：只标部件与「正向优点」，不套用失效模式
                if sent == '正向':
                    cat1 = (tax.cat1_of_part.get(part_name)
                            if part_name else '使用体验')
                    cat2 = _make_cat2(part_name, cat1, None) if part_name \
                        else '整体 · 正向优点'
                    ops.append(dict(
                        src=row_src, raw=text, snippet=cl, sentiment='正向',
                        cat1=cat1, cat2=cat2, cat3='', cat3_desc='',
                        part=part_name or '', platform=False,
                        concrete=concrete, doubt=False, star=row.get('star'),
                    ))
                    continue

                # 归类
                if mode:
                    cat1 = tax.cfg.get('mode_cat1', {}).get(mode) or \
                        next((m['cat1'] for m in tax.mode_list if m['name'] == mode),
                             '结构/功能配件')
                    cat2 = _make_cat2(part_name, cat1, mode)
                else:
                    cat1, cat2 = _fallback_cat1(cl, part_name, tax)
                doubt = (not mode) and (not part_name)
                ops.append(dict(
                    src=row_src, raw=text, snippet=cl, sentiment=sent,
                    cat1=cat1, cat2=cat2,
                    cat3=mode or '', cat3_desc=desc,
                    part=part_name or '', platform=False,
                    concrete=concrete, doubt=doubt, star=row.get('star'),
                ))
    return ops


# 一级大类 → 失效族群（用于生成可读的二级标签名）
CAT1_FAMILY = {
    'Listing预期不符': '预期不符',
    '结构/功能配件': '功能失效',
    '产品做工&材质': '做工材质',
    '尺寸贴合': '贴合问题',
    '外观手感': '外观手感',
    '包装物流': '包装物流',
    '使用体验': '使用体验',
    '性价比': '性价比',
    '其他': '其他',
}


def _guess_part(cat1):
    return {'产品做工&材质': '整体', '尺寸贴合': '尺寸适配',
            '外观手感': '外观手感', '包装物流': '包装物流',
            '使用体验': '使用体验', '性价比': '性价比'}.get(cat1, '整体')


def _make_cat2(part_name, cat1, mode):
    """生成可读的二级标签：『部件 · 失效族群』，无部件时退化为族群名"""
    family = CAT1_FAMILY.get(cat1, '其他')
    if part_name:
        return '%s · %s' % (part_name, family)
    return family


# 未指明具体部件/现象时的统一标签名（明确说明"原文没给落点"，不是分析失败）
UNSPEC_LABEL = '未指明（原文无具体落点）'


def _fallback_cat1(text, part, tax):
    """没有命中失效模式时的兜底归类。优先用已知部件反推一级大类。"""
    low = normalize(text)
    if part:
        cat1 = tax.cat1_of_part.get(part, '结构/功能配件')
        return cat1, _make_cat2(part, cat1, None)
    if re.search(r'\b(not as|not what|expected|advertis|misleading|'
                 r'deceptive|pictured|described|inaccurate|as stated|scam|rip off)\b', low):
        return 'Listing预期不符', '图文描述与实物不符'
    if re.search(r'\b(cheap|flimsy|quality|material|fragile|weak|sturdy|durable|thin|thick|'
                 r'poorly|badly|plastic|shabby|finish|scratch\w*|broke|broken|crack\w*)\b', low):
        return '产品做工&材质', '材质单薄/廉价感（感知做工）'
    if re.search(r'\b(fit|size|fits|fit well|tight|loose|snug|compatible|'
                 r'model|big|small|flush|align)\b', low):
        return '尺寸贴合', '尺寸/机型不适配'
    if re.search(r'\b(color|colour|shade|looks|style|design|beautiful|ugly)\b', low):
        return '外观手感', '颜色/外观与预期不符'
    if re.search(r'\b(box|package|packaging|arrived|damaged|missing|wrong item|'
                 r'shipping|delivery|late|come without|included)\b', low):
        return '包装物流', '包装/配件缺失或错发'
    if re.search(r'\b(use|using|used|easy|difficult|hard to|comfortable|'
                 r'interfere|operation|stick|adhesi\w*|residue|button|open|close)\b', low):
        return '使用体验', '使用过程问题'
    if re.search(r'\b(price|expensive|cheap|worth|cost|value|money|penny|dollar)\b', low):
        return '性价比', '价格/性价比不符'
    return '其他', UNSPEC_LABEL


# ======================================================================
# 统计
# ======================================================================
def build_stats(ops):
    """生成 维度 → 模式 → 原文 的树，以及二级标签视角的树"""
    neg = [o for o in ops if o['sentiment'] == '负面']
    negN = len(neg) or 1

    # 部件视角
    dim_map = defaultdict(lambda: defaultdict(list))
    for o in neg:
        dim_map[o.get('part') or UNSPEC_LABEL][(o['cat3'] or UNSPEC_LABEL,
                                              o.get('cat3_desc', ''))].append(o)
    dims = []
    for dim, modes in dim_map.items():
        tot = sum(len(v) for v in modes.values())
        children = []
        for (mode, desc), items in sorted(modes.items(), key=lambda x: -len(x[1])):
            children.append(dict(
                mode=mode, desc=desc, n=len(items),
                pct_in_dim=round(len(items) / tot * 100, 2),
                pct_of_neg=round(len(items) / negN * 100, 2),
                ret=sum(1 for x in items if x['src'] == '买家之声退货报告'),
                rev=sum(1 for x in items if x['src'] != '买家之声退货报告'),
            ))
        dims.append(dict(dim=dim, n=tot, pct_of_neg=round(tot / negN * 100, 2),
                         modes=children))
    dims.sort(key=lambda x: -x['n'])

    # 二级标签视角
    c2_map = defaultdict(list)
    for o in neg:
        c2_map[o['cat2']].append(o)
    cat2_tree = []
    for cat2, items in sorted(c2_map.items(), key=lambda x: -len(x[1])):
        sub = defaultdict(list)
        for o in items:
            sub[(o['cat3'] or UNSPEC_LABEL, o.get('cat3_desc', ''))].append(o)
        children = []
        for (mode, desc), its in sorted(sub.items(), key=lambda x: -len(x[1])):
            children.append(dict(
                key=mode, desc=desc, n=len(its),
                pct=round(len(its) / len(items) * 100, 2),
                ret=sum(1 for x in its if x['src'] == '买家之声退货报告'),
                rev=sum(1 for x in its if x['src'] != '买家之声退货报告'),
            ))
        cat2_tree.append(dict(
            cat1=items[0]['cat1'], cat2=cat2, n=len(items),
            pct_of_neg=round(len(items) / negN * 100, 2),
            ret=sum(1 for x in items if x['src'] == '买家之声退货报告'),
            rev=sum(1 for x in items if x['src'] != '买家之声退货报告'),
            subcats=children,
        ))
    return dict(dims=dims, cat2_tree=cat2_tree, negN=negN)
