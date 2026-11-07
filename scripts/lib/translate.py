# -*- coding: utf-8 -*-
"""
翻译：脚本只做「覆盖率校验 + 格式规范化」，翻译本体交给 Agent

设计理由（实测结论）：
  逐词/短语规则翻译在英语长句上必然产出「半中半英」劣质译文（实测 70.8% 混排），
  而半中半英比英文原文更糟 —— 既不准确也不好读。
  规则翻译只适合「短评价句」（≤8 词且全部命中），实测这部分质量可用。

因此：
  · 规则翻译 → 只处理短句，产出高质量中文
  · 长句 → 由 Agent 批量翻译（Agent 有真正的语言能力）
  · 本脚本 → 导出待译清单、校验译文覆盖率、规范化格式
"""
import io
import json
import os
import re
from collections import Counter

from dict_zh import PHRASES, WORDS

KEEP_EN = {
    'magsafe', 'mag safe', 'iphone', 'iphone duo', 'duo', 'anker', 'spigen',
    'idk', 'na', 'usb', 'type-c', 'torras', 'otterbox', 'speck', 'qi',
    'tpu', 'pc', 'supcase', 'nillkin', 'esr', 'apple',
}

_IRREGULAR = {
    'is': 'be', 'are': 'be', 'was': 'be', 'were': 'be', 'been': 'be',
    'am': 'be', 'being': 'be', 'has': 'have', 'had': 'have', 'does': 'do',
    'did': 'do', 'done': 'do', 'went': 'go', 'gone': 'go', 'made': 'make',
    'took': 'take', 'taken': 'take', 'came': 'come', 'fell': 'fall',
    'felt': 'feel', 'kept': 'keep', 'left': 'leave', 'broke': 'break',
    'broken': 'break', 'bought': 'buy', 'built': 'build', 'sent': 'send',
    'spent': 'spend', 'lost': 'lose', 'found': 'find', 'gave': 'give',
    'given': 'give', 'held': 'hold', 'wore': 'wear', 'worn': 'wear',
    'tore': 'tear', 'torn': 'tear', 'ran': 'run', 'stood': 'stand',
    'said': 'say', 'paid': 'pay', 'met': 'meet', 'led': 'lead',
    'put': 'put', 'read': 'read',
}

_SUFFIX_RULES = [
    ('ies', 'y'), ('ied', 'y'), ('ves', 'f'), ('ves', 'fe'),
    ('ing', ''), ('ing', 'e'), ('ers', 'er'), ('er', 'e'),
    ('es', ''), ('s', ''), ('ed', ''), ('ed', 'e'), ('d', ''),
    ('er', ''), ('est', ''), ('ly', ''), ('ness', ''),
]


def _stem(w):
    cands = []
    lw = w.lower()
    if lw in _IRREGULAR:
        cands.append(_IRREGULAR[lw])
    for suf, repl in _SUFFIX_RULES:
        if lw.endswith(suf) and len(lw) > len(suf) + 2:
            base = lw[:-len(suf)] + repl
            if base != lw:
                cands.append(base)
    if lw.endswith('ing') and len(lw) > 4 and lw[-3] == lw[-4]:
        cands.append(lw[:-3] + 'e')
    if lw.endswith('ed') and len(lw) > 3 and lw[-3] == lw[-2]:
        cands.append(lw[:-2])
    return cands


def _norm(s):
    s = s.replace("'", '').replace('\u2019', '')
    s = re.sub(r'[^a-z0-9 ]', ' ', s.lower())
    return re.sub(r'\s+', ' ', s).strip()


EXACT = {}
for en, zh in PHRASES:
    EXACT[_norm(en)] = zh

WORD_MAP = {en.lower(): zh for en, zh in WORDS}
PAT_WORD = re.compile(r"[a-z']+", re.I)

# 规则翻译只处理短评价句
MAX_SHORT_WORDS = 8


def cleanup(res):
    """规范化译文格式：中英间距、标点"""
    res = re.sub(r'\s+', ' ', res).strip()
    res = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', res)
    res = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[，。、；：！？）])', '', res)
    res = re.sub(r'(?<=[（])\s+(?=[\u4e00-\u9fff])', '', res)
    res = re.sub(r'(?<=[\u4e00-\u9fff]),\s*', '，', res)
    res = re.sub(r'(?<=[\u4e00-\u9fff])\s*\.\s*', '。', res)
    res = re.sub(r'(?<=[\u4e00-\u9fff])\s*!\s*', '！', res)
    res = re.sub(r'(?<=[\u4e00-\u9fff])\s*\?\s*', '？', res)
    res = re.sub(r'\s+([,.!;:?])', r'\1', res)
    res = re.sub(r'([,.!;:?])\s+', r'\1', res)
    return res.strip(' ,.;:')


def rule_translate(text, extra=None):
    """规则翻译短评价句。返回中文或 None（表示无法可靠翻译）"""
    if not text:
        return None
    extra = {k.lower(): v for k, v in (extra or {}).items()}
    low = text.replace("'", '').replace('\u2019', '').strip()

    n = _norm(low)
    if n in EXACT:
        return EXACT[n]

    words = PAT_WORD.findall(low)
    if len(words) > MAX_SHORT_WORDS:
        return None

    miss = []

    def sub(m):
        w = m.group(0)
        lw = w.lower()
        if lw in extra:
            return extra[lw]
        if lw in KEEP_EN:
            return w
        if lw in WORD_MAP:
            return WORD_MAP[lw]
        for c in _stem(lw):
            if c in extra:
                return extra[c]
            if c in WORD_MAP:
                return WORD_MAP[c]
        miss.append(lw)
        return w

    out = PAT_WORD.sub(sub, low)
    if miss:
        return None
    out = cleanup(out)
    if not re.search(r'[\u4e00-\u9fff]', out):
        return None
    return out


# ======================================================================
# Agent 翻译流程：导出待译清单 / 校验译文
# ======================================================================
def export_todo(items, out_path, extra=None):
    """
    导出待翻译清单（给 Agent 批量翻译用）
    items: [{'id':..., 'en':...}]
    输出 JSONL：{"id":..., "en":..., "zh":""}，Agent 填 zh 后回填
    """
    seen, uniq = set(), []
    for it in items:
        en = (it.get('en') or '').strip()
        if not en or en in seen:
            continue
        seen.add(en)
        # 规则能翻的先填上，Agent 只需处理剩下的
        zh = rule_translate(en, extra)
        uniq.append(dict(id=len(uniq), en=en, zh=zh or ''))
    with io.open(out_path, 'w', encoding='utf-8') as f:
        for u in uniq:
            f.write(json.dumps(u, ensure_ascii=False) + '\n')
    need = sum(1 for u in uniq if not u['zh'])
    return len(uniq), need


def validate(mapping, min_coverage=0.9):
    """
    校验译文覆盖率与质量
    mapping: {en: zh}
    返回 (覆盖率, 问题列表)
    """
    total = len(mapping)
    if not total:
        return 0.0, ['译文为空']
    no_zh = [k for k, v in mapping.items()
             if not v or not re.search(r'[\u4e00-\u9fff]', v)]
    mixed = []
    for k, v in mapping.items():
        if not v or not re.search(r'[\u4e00-\u9fff]', v):
            continue
        resid = [w for w in re.findall(r'[A-Za-z]{3,}', v)
                 if w.lower() not in KEEP_EN]
        if resid:
            mixed.append((k, v, resid))
    cov = (total - len(no_zh)) / total * 100
    issues = []
    if no_zh:
        issues.append('%d 条无中文' % len(no_zh))
    if mixed:
        issues.append('%d 条中英混排' % len(mixed))
    if cov < min_coverage * 100:
        issues.append('覆盖率 %.1f%% < 阈值 %.0f%%' % (cov, min_coverage * 100))
    return cov, issues


def apply_mapping(ops, mapping):
    """把译文贴回观点"""
    for o in ops:
        z = mapping.get(o['snippet']) or mapping.get(o['raw'])
        if z:
            o['zh'] = z
            o['zh_full'] = bool(re.search(r'[\u4e00-\u9fff]', z))
        else:
            o['zh'] = ''
            o['zh_full'] = False
    return ops
