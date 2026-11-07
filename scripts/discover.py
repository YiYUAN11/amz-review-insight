# -*- coding: utf-8 -*-
"""
部件发现 —— 从语料自动提炼「这个品类在抱怨什么部件」

用法：
  python discover.py --config taxonomy.json --out candidates.json
  python discover.py --files <xlsx...> --out candidates.json

输出：候选部件词 + 与各失效现象的共现次数 + 原始证据句。
脚本负责统计，**语义判断（这是不是真部件）交给 Agent**。
"""
import argparse
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'lib'))
sys.path.insert(0, HERE)

# 用扁平导入（与 run.py 一致），避免 lib.discover 与 lib 包自我循环导入
from discover_lib import discover, PROBLEM_ANCHORS
from engine import normalize

# 跨品类通用失效现象（用于共现矩阵）
PHEN = {
    '断裂': r'\b(broke|broken|snapped|crack\w*|shatter\w*|tore|torn|split|separat\w*|fell apart)\b',
    '脱落': r'\b(fall\w* off|came (off|out)|pop\w* (off|out)|detach\w*|come off|comes off)\b',
    '松动/不稳': r'\b(loose|wobbl\w*|unstable|not secure|not stable|shak\w*|comes loose)\b',
    '撑不住/承重': r'\b(not (strong|sturdy|stable)|too weak|doesn.t hold|won.t hold|collapse\w*|not strong enough)\b',
    '过薄/易脆': r'\b(flimsy|fragile|thin|too thin|too soft|flexible)\b',
    '不贴合/尺寸': r'\b(fit|doesn.t fit|didn.t fit|loose fit|too (big|small|tight)|not snug)\b',
    '不工作/失效': r'\b(not work\w*|doesn.t work|stopped working|failed|quit working)\b',
    '充不进电': r'\b(charg\w*|power|battery|plug)\b',
    '刮花/磨损': r'\b(scratch\w*|wear\w*|fade\w*|peel\w*|scuff\w*|corrode\w*|rust\w*)\b',
    '异响/异动': r'\b(noise|loud|noisy|click\w*|rattle\w*|creak\w*|squeak\w*|wobble)\b',
    '遮挡/干涉': r'\b(block\w*|interfer\w*|obstruct\w*|in the way|cover\w* the)\b',
    '颜色/外观': r'\b(color|colour|shade|look\w*|design|style|finish|appear\w*)\b',
    '漏/不密封': r'\b(leak\w*|not seal\w*|seal\w*|water|tight\w* seal)\b',
}


def texts_from_files(paths, text_columns=None):
    """读 xlsx 提取文本列。逐表精准识别，并打印选择理由。"""
    import openpyxl
    out = []
    for p in paths:
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        used_cols = set()
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            headers = [str(h).strip() if h is not None else '' for h in rows[0]]
            col = pick_text_col(headers, rows, text_columns, p, ws.title,
                                exclude=used_cols)
            if col is None:
                print('  · %s/%s → 未找到反馈文本列，跳过'
                      % (os.path.basename(p), ws.title))
                continue
            used_cols.add(col)
            sc, why = explain_pick(headers, rows, col)
            print('  · %s/%s → 列「%s」(score=%d) %s'
                  % (os.path.basename(p), ws.title, headers[col], sc,
                     '; '.join(why[:3])))
            for r in rows[1:]:
                if col < len(r) and r[col] is not None:
                    t = str(r[col]).strip()
                    if t:
                        out.append(t)
        wb.close()
    return out


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
    