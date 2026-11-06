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
    out = pat
    for a, b in _CONTRACTION_FIX:
        out = re.sub(a, b, out)
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
        # 部件 → 该部件允许的失效模式（空表示不限）
        self.part_modes = {p['name']: p.get('modes', []) for p in self.parts}
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
        part 已知时，优先用该部件允许的模式；part 未知时用全局模式表。
        """
        low = normalize(text)
        # 第一轮：部件白名单内的模式
        if part and self.part_modes.get(part):
            for m in self.mode_list:
                if m['name'] not in self.part_modes[part]:
                    continue
                for rx in m['rx']:
                    if rx.search(low):
                        return m['name'], m['desc']
        # 第二轮：全局模式表
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
    r'loose|wobbly|unstable|defective|damaged|scratch\w*|tore|torn|split|'
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
    r'not compatible|incompatible|falls? off|comes? off|pops? off|'
    r'comes? apart|fell apart|comes? loose|not stay|not secure|not stable|'
    r'not strong|not sturdy|not durable|not comfortable|not smooth|not flush|'
    r'not worth|not happy|not pleased|not what i expected|not good|not great|'
    r'don.?t (like|buy|recommend|waste)|wouldn.?t (recommend|buy)|'
    r'doesn.?t (work|fit|protect)|no protection|only (protects|the back)|'
    r'not (a )?full case|incomplete|scam|rip off|overpriced|'
    r'could be (better|improved)|needs? (to be|improvement|a better)|'
    r'flaw\w*|issue\w* with|problem\w* with)\b',
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
    r'solid (case|product)|feels great|looks great)\b', re.I)

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


def judge_sentiment(text, star=None):
    """
    判定情感。
    优先级：明确正面 > 否定+正面消歧 > 明确负面信号 > 否定词 > 星级参考 > 中性
    """
    low = normalize(text)

    # 1) 明确正面
    if STRONG_POS_RX.search(low) and not NEGATOR_RX.search(low):
        return '正向'

    # 2) 否定词 + 正面词 → 实为好评（"no issues at all"、"a no brainer"）
    if NEG_POS_PAIR_RX.search(low):
        return '正向'

    # 3) 明确负面信号（broken/flimsy/low quality…），即使没有 not 也算负面
    if NEGATIVE_RX.search(low):
        return '负面'

    # 4) 否定词 → 负面
    if NEGATOR_RX.search(low):
        return '负面'

    # 5) 正面词但带否定 → 负面（"not good"、"doesn't like"）
    if POSITIVE_RX.search(low):
        return '负面'

    # 6) 星级参考（评论表）
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
        seen = set()
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
                    src=source_name, raw=text, snippet=part,
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
                        src=source_name, raw=text, snippet=cl, sentiment=emo2,
                        cat1='Listing预期不符' if '预期不符' in pname2 else '其他',
                        cat2=pname2, cat3='', platform=True, concrete=False,
                        doubt=False, star=row.get('star'),
                    ))
                    continue
                seen.add(cn)
                part_name = tax.detect_part(cl) or tax.detect_part_loose(cl)
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
                        src=source_name, raw=text, snippet=cl, sentiment='正向',
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
                    src=source_name, raw=text, snippet=cl, sentiment=sent,
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
    return '其他', '其他（未细分）'


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
        dim_map[o.get('part') or '未指明部件'][(o['cat3'] or '未细分',
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
            sub[(o['cat3'] or '未细分', o.get('cat3_desc', ''))].append(o)
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
