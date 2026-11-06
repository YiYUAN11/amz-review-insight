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
