# -*- coding: utf-8 -*-
"""
部件发现引擎 —— 从语料自动提炼「这个品类在抱怨什么部件」

思路：
1. 先用一组「失效现象锚点」（broken/loose/flimsy/doesn't fit…）定位抱怨句。
2. 在抱怨句里统计高频名词短语（候选部件）。
3. 用「部件 × 现象」共现矩阵给出证据，便于判断哪个词真是部件。
4. 同时给出按长度/词性的候选短语（n-gram）。

脚本负责统计与排序；**语义判断（这是不是真部件）交给 Agent**。
"""
import io
import json
import os
import re
from collections import Counter, defaultdict

from engine import normalize, norm_key

# 抱怨/提及锚点：出现这些词说明这句在描述问题
PROBLEM_ANCHORS = re.compile(
    r"\b(broke|broken|break|snapped|crack\w*|shatter\w*|flimsy|fragile|loose|loosely|"
    r"weak|wobbl\w*|defective|damag\w*|scratch\w*|tore|torn|split|separat\w*|detach\w*|"
    r"fall\w* (off|apart)|came (off|out)|pop\w* (off|out)|does not work|doesnt work|"
    r"not work\w*|won't work|wont work|stopped working|failed|"
    r"doesn't fit|does not fit|didn't fit|did not fit|not fit|loose fit|too (big|small|thick|thin|"
    r"loose|tight|bulky|heavy|light|short|long|wide|narrow)|"
    r"not (protect\w*|cover\w*|secure|stable|strong|sturdy|durable|comfortable|"
    r"charge\w*|charge|work|fit|stick|adhere|hold|support)|"
    r"can't|cannot|won't|wont|hard to (open|close|use|install|remove)|"
    r"issue|problem|bad|poor|cheap|awful|terrible|horrible|disappoint\w*|wrong|"
    r"missing|different|uncomfortable|slipp\w*|stuck|jam\w*|noise|loud|click\w*|"
    r"rattle|wobble|creak|squeak|loosening|bubbl\w*|scratch\w*|tear\w*|fade\w*|"
    r"yellow\w*|discolor\w*|warped|bent|deform\w*|dented|leak\w*|break\w*)\b", re.I)

# 明显不是部件的词（停用表）
STOP_NOUNS = {
    'case', 'item', 'product', 'thing', 'order', 'purchase', 'amazon', 'seller',
    'phone', 'device', 'part', 'piece', 'time', 'day', 'week',
    'month', 'year', 'money', 'price', 'quality', 'expectation', 'review',
    'star', 'comment', 'issue', 'problem', 'lot', 'bit', 'kind',
    'i', 'it', 'this', 'that', 'they', 'them', 'me', 'my', 'we', 'he', 'she',
    'the', 'and', 'but', 'or', 'so', 'very', 'too', 'not', 'no', 'yes',
    'return', 'refund', 'replacement', 'listing', 'description',
    'picture', 'image', 'photo', 'website', 'brand', 'company',
    'customer service', 'chat', 'email', 'message', 'reply', 'response',
    'sizing', 'size', 'material', 'color', 'colour', 'design',
    'look', 'appearance', 'feel', 'weight', 'value',
    'protection', 'coverage', 'support', 'fit', 'function', 'feature',
    'accessory', 'accessories', 'package', 'box', 'bag',
    # 功能/虚词
    'on', 'in', 'at', 'of', 'for', 'with', 'from', 'to', 'by', 'as', 'is',
    'was', 'are', 'were', 'be', 'been', 'has', 'have', 'had', 'will',
    'would', 'can', 'could', 'should', 'may', 'might', 'must', 'do', 'does',
    'did', 'up', 'out', 'off', 'down', 'over', 'under', 'into', 'onto',
    'then', 'than', 'when', 'while', 'after', 'before', 'during', 'since',
    'use', 'used', 'using', 'make', 'makes', 'made', 'get', 'got', 'put',
    'take', 'took', 'keep', 'know', 'think', 'thought', 'want', 'need',
    'like', 'love', 'hate', 'seem', 'seems', 'look', 'looks', 'felt',
    'feel', 'feels', 'changed', 'change', 'added', 'add', 'has', 'having',
    'will', 'would', 'could', 'never', 'always', 'often', 'sometimes',
    'thing', 'things', 'something', 'anything', 'nothing', 'everything',
    'someone', 'anyone', 'everyone', 'myself', 'itself', 'himself',
    'really', 'just', 'still', 'even', 'also', 'only', 'much', 'more',
    'most', 'less', 'least', 'way', 'quite', 'pretty', 'some', 'every',
    'both', 'each', 'few', 'many', 'here', 'where', 'what', 'which',
    'who', 'how', 'why', 'because', 'though', 'although', 'however',
    'otherwise', 'therefore', 'moreover', 'furthermore', 'meanwhile',
    'nevertheless', 'up', 'left', 'right', 'top', 'bottom', 'middle',
    'center', 'back', 'front', 'side', 'sides', 'area', 'part', 'parts',
    'end', 'ends', 'edge', 'edges', 'corner', 'corners', 'whole',
    'entire', 'inside', 'outside', 'between', 'through', 'during',
    'before', 'after', 'again', 'once', 'twice', 'thrice',
    'much', 'many', 'lot', 'plenty', 'enough', 'more', 'less',
    'good', 'bad', 'great', 'nice', 'fine', 'okay', 'ok', 'well',
    'new', 'old', 'first', 'second', 'third', 'last', 'next',
    'day', 'days', 'week', 'weeks', 'month', 'months', 'year', 'years',
    'hour', 'hours', 'minute', 'minutes', 'second', 'seconds',
    'time', 'times', 'half', 'one', 'two', 'three', 'four', 'five',
    'six', 'seven', 'eight', 'nine', 'ten', 'hundred',
    'inch', 'inches', 'cm', 'mm', 'lb', 'lbs', 'oz', 'gram', 'g',
    'dollars', 'dollar', 'cent',
    'email', 'sent', 'received', 'reply', 'text',
}


def extract_candidates(texts, max_n=4):
    """从文本里抽 n-gram 候选名词短语"""
    counter = Counter()
    for t in texts:
        low = normalize(t)
        toks = re.findall(r"[a-z][a-z'\-]+", low)
        for n in range(1, max_n + 1):
            for i in range(len(toks) - n + 1):
                gram = toks[i:i + n]
                g = ' '.join(gram)
                if not g or len(g) < 3:
                    continue
                # 含停用词的组合直接丢（"the phone" / "on the" 这类不是部件）
                if any(w in STOP_NOUNS for w in gram):
                    continue
                # 不能是动词/副词/代词
                if re.search(r'\b(not|very|too|so|just|really|quite|dont|doesnt|'
                             r'didnt|wont|cant|cannot|and|but|or|is|was|are|were|'
                             r'be|been|being|have|has|had|will|would|can|'
                             r'i|my|me|we|you|it|its|this|that|they|them|'
                             r'no|yes|if|then|than|when|while|after|before|'
                             r'for|with|from|into|onto|over|under|about|'
                             r'like|get|got|put|take|make|made|use|used|'
                             r'know|think|want|need|feel|felt|look|seem|'
                             r'change|changed|add|added|go|going|come|came)\b', g):
                    continue
                # 词尾像名词
                if not re.search(r'(s|n|t|r|e|er|ing|ed|al|ic|ical|ish|less|ment|ness|'
                                 r'able|ible|ure|ade|ock|ook|een|ide|obe|ipe|'
                                 r'ine|ay|ry|ty|gy|ph|sh|ch|x|z|ss|er|or)$', g):
                    continue
                counter[g] += 1
    return counter


def discover(texts, top=120, min_count=2):
    """返回候选部件 + 证据"""
    problem_texts = [t for t in texts if PROBLEM_ANCHORS.search(normalize(t))]
    cand = extract_candidates(problem_texts)

    # 过滤：只保留在「抱怨句」中明显高频的
    cands = [(w, n) for w, n in cand.most_common(top * 3) if n >= min_count]

    # 证据：每个候选的原始句
    evidence = defaultdict(list)
    for t in problem_texts:
        low = normalize(t)
        for w, _ in cands[:top * 2]:
            if re.search(r'(?<![a-z])' + re.escape(w) + r'(?![a-z])', low):
                if len(evidence[w]) < 6:
                    evidence[w].append(t.strip()[:180])

    # 按「跨现象多样性」重排：一个真部件通常与多种现象共现
    PHEN = {
        '断裂': r'\b(broke|broken|snapped|crack\w*|shatter\w*|tore|torn|split|separat\w*)\b',
        '脱落': r'\b(fall\w* off|came (off|out)|pop\w* (off|out)|detach\w*|loose)\b',
        '松动/不稳': r'\b(loose|wobbl\w*|unstable|not secure|not stable|shak\w*)\b',
        '撑不住': r'\b(not (strong|sturdy|stable)|too weak|doesn.t hold|won.t hold|collapse\w*)\b',
        '过薄/脆': r'\b(flimsy|fragile|thin|too thin|too soft|flexible)\b',
        '不贴合': r'\b(fit|doesn.t fit|didn.t fit|loose fit|too (big|small|tight))\b',
        '不工作': r'\b(not work\w*|doesn.t work|stopped working|failed)\b',
        '充不进电': r'\b(charg\w*|power|battery)\b',
        '刮花/磨损': r'\b(scratch\w*|wears?|fade\w*|peel\w*|scuff\w*)\b',
        '异响': r'\b(noise|loud|noisy|click\w*|rattle\w*|creak\w*|squeak\w*)\b',
        '遮挡/干涉': r'\b(block\w*|interfer\w*|obstruct\w*|cover\w*|in the way)\b',
        '颜色/外观': r'\b(color|colour|shade|look\w*|design|style)\b',
    }
    phens = {k: re.compile(v, re.I) for k, v in PHEN.items()}

    rows = []
    for w, n in cands:
        if n < min_count:
            continue
        ev = evidence.get(w, [])
        coex = Counter()
        for t in ev:
            for k, rx in phens.items():
                if rx.search(normalize(t)):
                    coex[k] += 1
        rows.append(dict(
            word=w, count=n, diversity=len(coex),
            coex=dict(coex.most_common()),
            samples=ev[:4],
        ))
    rows.sort(key=lambda r: (-r['diversity'], -r['count']))
    return rows[:top], len(problem_texts), len(texts)


def to_candidates(rows, text_sample):
    """转成 taxonomy 配置里的 parts 草案"""
    out = []
    for r in rows:
        out.append(dict(
            name=r['word'],
            aliases=[],
            cat1='结构/功能配件',
            modes=[],
        ))
    return out


# ======================================================================
# 文本列精准识别
# ======================================================================
# 表头里像「反馈/评论/评价」的关键词（多语言 + 常见变体）
FEEDBACK_HEADER_RX = re.compile(
    r'反馈|評論|评论|評價|评价|評测|差评|好评|退货原因|退货理由|退貨原因|'
    r'买家.{0,4}(反馈|留言|评价|评论)|客服.{0,4}(留言|消息)|'
    r'内容|描述|說明|说明|正文|'
    r'feedback|review|comment|remark|verbatim|response|'
    r'what.{0,6}wrong|why.{0,6}return|customer.{0,6}(comment|say|feedback|note)|'
    r'voice.{0,3}of.{0,3}customer|voc\b|'
    r'text|content|message|body|reason|description',
    re.I)

# 明确不是反馈内容的列（ID / 元数据 / 数值）
NON_FEEDBACK_RX = re.compile(
    r'标题|品名|產品名|商品名|产品名称|'
    r'店铺|店鋪|国家|國家|asin|fnsku|msku|sku\b|spu|'
    r'订单号|訂單號|order\s*(id|no|num)|invoice|'
    r'日期|date|时间|時間|'
    r'图片|圖片|image|photo|img|thumbnail|前台|'
    r'备注|備註|remark|note\b|'
    r'数量|數量|qty|quantity|amount|price|金额|單價|售价|'
    r'asin\s*标题|listing|类目|category|brand|品牌|'
    r'序号|序號|index|no\b|id\b',
    re.I)

# 反馈文本的典型形态特征
FEEDBACK_CONTENT_RX = re.compile(
    r'\b(not|doesn.t|didn.t|wont|can.t|too|very|but|and|it|is|i|my|'
    r'was|were|have|has|no|so|they|this|that|with|for)\b', re.I)
SENTENCE_RX = re.compile(r'[.!?;]|\|')
CJK_RX = re.compile(r'[\u4e00-\u9fff]')


def _col_stats(rows, idx):
    """一列的统计特征"""
    vals = []
    for r in rows[1:401]:
        if idx < len(r) and r[idx] is not None:
            vals.append(str(r[idx]))
    if not vals:
        return dict(n=0, fill=0, avg=0, uniq=0, pipe=0, cjk=0, sent=0)
    filled = [v for v in vals if v.strip()]
    return dict(
        n=len(vals), fill=len(filled) / len(vals),
        avg=sum(len(v) for v in filled) / max(1, len(filled)),
        uniq=len(set(v.strip().lower() for v in filled)) / max(1, len(filled)),
        pipe=sum(1 for v in filled if '|' in v) / max(1, len(filled)),
        cjk=sum(1 for v in filled if CJK_RX.search(v)) / max(1, len(filled)),
        sent=sum(1 for v in filled if SENTENCE_RX.search(v)) / max(1, len(filled)),
    )


def _col_has_text(rows, i):
    s = _col_stats(rows, i)
    return s['fill'] > 0.4 and s['avg'] > 10


def score_col(headers, rows, idx):
    """给一列打「像反馈文本」的分，返回 (分数, 理由列表)"""
    reasons = []
    h = headers[idx] if idx < len(headers) else ''
    s = _col_stats(rows, idx)
    if not s['n']:
        return -1, ['空列']

    score = 0.0

    # 表头信号（最强）
    if h:
        if FEEDBACK_HEADER_RX.search(h) and not NON_FEEDBACK_RX.search(h):
            score += 100
            reasons.append('表头命中「%s」' % h)
        elif NON_FEEDBACK_RX.search(h):
            score -= 60
            reasons.append('表头像元数据「%s」' % h)

    # 内容信号
    if s['avg'] >= 25:
        score += 25
        reasons.append('平均长度 %.0f' % s['avg'])
    elif s['avg'] >= 12:
        score += 12
        reasons.append('平均长度 %.0f' % s['avg'])
    else:
        score -= 25
        reasons.append('平均长度过短 %.0f' % s['avg'])

    if s['fill'] > 0.8:
        score += 12
    elif s['fill'] > 0.4:
        score += 5
    else:
        score -= 30

    # 高重复度 → 多半是枚举/编号，不是自由文本
    if s['uniq'] < 0.12 and s['n'] > 20:
        score -= 30
        reasons.append('重复度极高(%.0f%% 唯一)' % (s['uniq'] * 100))
    elif s['uniq'] > 0.5:
        score += 15
        reasons.append('唯一值 %.0f%%' % (s['uniq'] * 100))

    # 管道分隔 → 平台下拉理由结构（强信号）
    if s['pipe'] > 0.3:
        score += 30
        reasons.append('管道分隔 %.0f%%（像 VOA 反馈）' % (s['pipe'] * 100))

    # 有中文 → 可能是平台侧的中文备注/翻译列
    if s['cjk'] > 0.5:
        score += 8
        reasons.append('含中文 %.0f%%' % (s['cjk'] * 100))

    # 句子特征
    if s['sent'] > 0.25:
        score += 8
        reasons.append('含句读/分隔 %.0f%%' % (s['sent'] * 100))

    # 常见虚词密度
    probe = [str(r[idx]) for r in rows[1:81] if idx < len(r) and r[idx]]
    if probe:
        hits = sum(1 for v in probe if FEEDBACK_CONTENT_RX.search(v))
        ratio = hits / len(probe)
        if ratio > 0.5:
            score += 12
            reasons.append('口语虚词 %.0f%%' % (ratio * 100))

    return score, reasons


def pick_text_col(headers, rows, text_columns=None, path=None, sheet=None,
                  exclude=None):
    """
    精准识别文本列。优先级：
      1) 配置显式指定（文件名或工作表名）
      2) 全列打分，取最高分
      3) 同一文件已选中的列不重复选
    返回列索引
    """
    base = os.path.basename(path) if path else ''
    if text_columns:
        for key in ([sheet] if sheet else []) + [base]:
            if key and key in text_columns:
                want = text_columns[key]
                if want in headers:
                    return headers.index(want)

    scored = []
    for i, h in enumerate(headers):
        if exclude and i in exclude:
            continue
        sc, why = score_col(headers, rows, i)
        scored.append((sc, i, h, why))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < 20:
        return None
    return scored[0][1]


def explain_pick(headers, rows, idx):
    sc, why = score_col(headers, rows, idx)
    return sc, why
