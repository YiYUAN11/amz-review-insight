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

from lib.discover import discover, PROBLEM_ANCHORS
from lib.engine import normalize

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--files', nargs='*', help='输入 xlsx')
    ap.add_argument('--config', help='taxonomy.json（从里面读 inputs）')
    ap.add_argument('--out', default='candidates.json')
    ap.add_argument('--top', type=int, default=60)
    a = ap.parse_args()

    if a.config:
        cfg = json.load(io.open(a.config, encoding='utf-8'))
        files = cfg.get('inputs', [])
    else:
        files = a.files or []
    if not files:
        print('需要 --files 或 --config')
        return

    print('读取 %d 个文件…' % len(files))
    texts = texts_from_files(files, cfg.get('text_columns') if a.config else None)
    print('文本 %d 条' % len(texts))

    rows, n_prob, n_all = discover(texts, top=a.top, min_count=2)
    print('抱怨句 %d / 全部 %d' % (n_prob, n_all))
    print()
    print('%-28s %6s %6s  %s' % ('候选部件', '次数', '现象数', '共现现象'))
    print('-' * 100)
    for r in rows:
        print('%-28s %6d %6d  %s' % (
            r['word'], r['count'], r['diversity'],
            ', '.join('%s:%d' % (k, v) for k, v in list(r['coex'].items())[:5])))

    out = dict(candidates=rows, n_texts=n_all, n_problem=n_prob,
               inputs=files)
    json.dump(out, io.open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n已写入 %s' % a.out)
    print('\n下一步：阅读上面的候选与证据样本，把真正的部件写进 taxonomy.json 的 parts 数组。')
    print('  parts[i] = { name, aliases:[英文别名], cat1:一级大类, modes:[允许的失效模式] }')


if __name__ == '__main__':
    main()
