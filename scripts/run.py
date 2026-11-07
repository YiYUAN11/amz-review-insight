# -*- coding: utf-8 -*-
"""
亚马逊退货 & 评论洞察分析 —— 端到端主流程

用法：
  python run.py --probe <文件...>                    探查输入文件
  python run.py --config taxonomy.json --out-dir out  全流程
  python run.py --config taxonomy.json --out-dir out --audit   抽样复核
"""
import argparse
import io
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'lib'))
sys.path.insert(0, HERE)

import engine
from engine import (Taxonomy, split_opinions, build_stats, normalize, norm_key,
                    UNSPEC_LABEL)
import io_excel
import io_html
import io_md


# ======================================================================
# 文件读取
# ======================================================================
def read_workbooks(paths):
    """读 xlsx → [{file, path, sheet, headers, rows(list[dict]), _rows(list[tuple])}]"""
    import openpyxl
    out = []
    for p in paths:
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            headers = [str(h).strip() if h is not None else '' for h in rows[0]]
            data = []
            for r in rows[1:]:
                if all(c is None or str(c).strip() == '' for c in r):
                    continue
                d = {}
                for i, h in enumerate(headers):
                    if not h:
                        continue
                    d[h] = (r[i] if i < len(r) else None)
                d['_row'] = len(data) + 2
                data.append(d)
            out.append(dict(file=os.path.basename(p), path=p, sheet=ws.title,
                            headers=headers, rows=data, _rows=rows))
        wb.close()
    return out

def probe(paths):
    """探查：打印每个表的工作表、表头、样例行"""
    for wb in read_workbooks(paths):
        print('=' * 70)
        print('文件：%s  工作表：%s  行数：%d' % (wb['file'], wb['sheet'], len(wb['rows'])))
        print('表头：%s' % wb['headers'])
        for r in wb['rows'][:3]:
            items = [(k, str(v)[:70]) for k, v in r.items()
                     if k != '_row' and v is not None and str(v).strip()]
            print('   行%-4s %s' % (r['_row'], items))
        # 文本列候选
        cand = []
        for h in wb['headers']:
            if not h:
                continue
            vals = [str(r.get(h) or '') for r in wb['rows'][:200]]
            non_empty = sum(1 for v in vals if v.strip())
            avg = sum(len(v) for v in vals) / max(1, len(vals))
            if non_empty > len(vals) * 0.5 and avg > 8:
                cand.append((h, non_empty, round(avg, 1)))
        if cand:
            print('   ▸ 文本列候选（列名, 非空数, 平均长度）：%s' % cand)
        print()


def pick_text_column(wb, cfg, exclude=None):
    """精准识别文本列（多信号打分：表头语义 + 内容特征）"""
    from discover_lib import pick_text_col
    return pick_text_col(wb['headers'], wb['_rows'], cfg.get('text_columns', {}),
                         wb['path'], wb['sheet'], exclude=exclude)


def pick_star_column(wb):
    for i, h in enumerate(wb['headers']):
        if h and re.search(r'星|rating|stars|score', h, re.I):
            return i
    return None


def pick_source_label(wb):
    """判断这个表是退货报告还是评论"""
    joined = ' '.join(wb['headers']).lower()
    # 有星级列 → 评论
    if pick_star_column(wb) is not None:
        return '买家评论'
    if re.search(r'评论|review|星级|stars?|评分|vine|vp评论|内容\(翻译\)', joined):
        return '买家评论'
    if re.search(r'退货|return|refund|退货原因|voice', joined):
        return '买家之声退货报告'
    return wb['sheet']


def extract_rows(wb, text_idx, star_idx, src):
    """按列索引取值"""
    rows = []
    for r in wb['rows']:
        t = r.get(wb['headers'][text_idx]) if text_idx < len(wb['headers']) else None
        if t is None:
            continue
        t = str(t).strip()
        if not t:
            continue
        star = None
        if star_idx is not None and star_idx < len(wb['headers']):
            try:
                star = float(r.get(wb['headers'][star_idx]))
            except (TypeError, ValueError):
                star = None
        rows.append(dict(text=t, star=star, src=src, row=r['_row']))
    return rows


def avg_len_by_idx(rows, headers, idx):
    if not rows or idx is None or idx >= len(headers):
        return 0
    col = headers[idx]
    return sum(len(r.get(col) or '') for r in rows) / len(rows)


META_SHEET_RX = re.compile(
    r'^(note|notes|说明|备注|readme|about|关于|info|信息|'
    r'copyright|版权|使用说明|help|帮助|faq|联系|contact|'
    r'sellersprite|卖家精灵|汇总说明)', re.I)

META_TEXT_RX = re.compile(
    r'(官网|客服电话|微信客服|插件使用指南|https?://|'
    r'插件|安装说明|使用方法|版权|copyright)', re.I)


def _is_meta_sheet(wb, text_idx):
    """判断是否说明/元信息表（非评论数据）"""
    if META_SHEET_RX.search(wb['sheet'] or ''):
        return True
    if not wb['headers']:
        return True
    # 单元格内容像说明文字
    vals = [str(r.get(wb['headers'][text_idx]) or '')
            for r in wb['rows'][:20] if text_idx < len(wb['headers'])]
    if vals and sum(1 for v in vals if META_TEXT_RX.search(v)) / len(vals) > 0.6:
        return True
    return False


# ======================================================================
# 证据挑选
# ======================================================================
def pick_evidence(items, k=4, maxlen=200):
    seen, scored = set(), []
    for o in items:
        s = (o.get('snippet') or '').strip()
        if len(s) < 8:
            continue
        k2 = ''.join(c for c in s.lower() if c.isalnum())[:28]
        if k2 in seen:
            continue
        seen.add(k2)
        low = s.lower()
        w = len(s.split())
        sc = 0
        if o.get('concrete'):
            sc += 4
        if 6 <= w <= 26:
            sc += 3
        elif w < 4:
            sc -= 6
        for kw in ('broke', 'broken', 'crack', 'snapped', 'loose', 'spin', 'hold',
                   'fit', 'bubble', 'lift', 'charge', 'magnet', 'flimsy', 'thin',
                   'hinge', 'stand', 'ring', 'corner', 'frame', 'weak', 'warp',
                   'bent', 'noise', 'protect', 'cover', 'stick', 'peel', 'zip',
                   'button', 'pocket', 'install', 'drop', 'scratch', 'leak'):
            if kw in low:
                sc += 2
                break
        scored.append((sc, w, s, o))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [dict(t=s[:maxlen], src=o['src'], zh=o.get('zh', ''),
                  mode=o.get('cat3', ''), cat3=o.get('cat3', ''), part=o.get('part', ''),
                  sent=o.get('sentiment', ''))
            for _, _, s, o in scored[:k]]


def uniq_evidence(items, limit=250):
    seen, out = set(), []
    for o in items:
        s = (o.get('snippet') or '').strip()
        if len(s) < 3:
            continue
        k = ''.join(c for c in s.lower() if c.isalnum())[:40]
        if k in seen:
            continue
        seen.add(k)
        out.append(dict(t=s[:220], src=o['src'], zh=o.get('zh', ''),
                        sent=o.get('sentiment', ''), mode=o.get('cat3', ''),
                        cat3=o.get('cat3', ''), part=o.get('part', '')))
        if len(out) >= limit:
            break
    return out


# ======================================================================
# 主流程
# ======================================================================
def run(cfg_path, out_dir, title, audit=False, sample=60, zh_file=None, strict=False):
    cfg = json.load(io.open(cfg_path, encoding='utf-8'))
    tax = Taxonomy(cfg)

    wbs = read_workbooks(cfg['inputs'])
    all_rows = []
    for wb in wbs:
        tc = pick_text_column(wb, cfg)
        if tc is None:
            print('  · %s/%s  未识别到反馈文本列，跳过' % (wb['file'], wb['sheet']))
            continue
        # 打印识别依据，便于人工核验
        from discover_lib import explain_pick
        sc, why = explain_pick(wb['headers'], wb['_rows'], tc)
        print('  · %s/%s' % (wb['file'], wb['sheet']))
        print('      文本列「%s」 score=%d  %s'
              % (wb['headers'][tc], sc, '; '.join(why[:4])))
        # 明显不是评论数据的表（说明页/元信息/统计表）
        src0 = pick_source_label(wb)
        if src0 in ('买家之声退货报告', '买家评论'):
            src = src0
        elif _is_meta_sheet(wb, tc):
            print('      判定为说明/元信息表，跳过')
            continue
        else:
            src = src0
        sc_star = pick_star_column(wb)
        print('      来源=%s  星级列=%s  行数=%d'
              % (src, wb['headers'][sc_star] if sc_star is not None else '无',
                 len(wb['rows'])))
        all_rows.extend(extract_rows(wb, tc, sc_star, src))

    if not all_rows:
        raise SystemExit('没有可用文本行，请检查 text_columns 配置')

    ops = split_opinions(all_rows, tax, '买家之声退货报告')

    # ---- 翻译 ----
    # 优先用外部译文映射（Agent 翻译产出）；缺失部分用规则翻译补短句
    zh_map = {}
    if zh_file and os.path.exists(zh_file):
        for line in io.open(zh_file, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get('zh'):
                zh_map[d['en']] = d['zh']
        print('  载入外部译文 %d 条（来自 %s）' % (len(zh_map), os.path.basename(zh_file)))
    from translate import apply_mapping, rule_translate
    apply_mapping(ops, zh_map)
    # 未覆盖的短句用规则翻译补上
    filled = 0
    for o in ops:
        if not o.get('zh'):
            z = rule_translate(o['snippet'], cfg.get('extra_translations', {}))
            if z:
                o['zh'] = z
                filled += 1
        if not o.get('raw_zh'):
            z = rule_translate(o['raw'], cfg.get('extra_translations', {}))
            o['raw_zh'] = z or ''
    n_zh = sum(1 for o in ops if o.get('zh'))
    print('  译文覆盖 %d/%d (%.1f%%)，其中规则补齐 %d 条'
          % (n_zh, len(ops), n_zh / max(1, len(ops)) * 100, filled))

    N = len(ops)
    neg = [o for o in ops if o['sentiment'] == '负面']
    negN = len(neg) or 1
    pos = [o for o in ops if o['sentiment'] == '正向']
    neu = [o for o in ops if o['sentiment'] == '中性']

    # ---- 统计 ----
    st = build_stats(ops)

    # 部件维度 → 模式 → 证据
    dim_groups = defaultdict(lambda: defaultdict(list))
    for o in neg:
        dim_groups[o.get('part') or '未指明部件'][(o['cat3'] or '未指明（原文无具体落点）',
                                                  o.get('cat3_desc', ''))].append(o)
    dims = []
    for dim, modes in dim_groups.items():
        tot = sum(len(v) for v in modes.values())
        children = []
        for (mode, desc), items in sorted(modes.items(), key=lambda x: -len(x[1])):
            children.append(dict(
                mode=mode, phen=desc, n=len(items),
                pct_in_dim=round(len(items) / tot * 100, 2),
                pct_of_neg=round(len(items) / negN * 100, 2),
                ret=sum(1 for x in items if x['src'] == '买家之声退货报告'),
                rev=sum(1 for x in items if x['src'] != '买家之声退货报告'),
                quotes=pick_evidence(items, 4)))
        dims.append(dict(dim=dim, n=tot, pct_of_neg=round(tot / negN * 100, 2),
                         modes=children))
    dims.sort(key=lambda x: -x['n'])

    # 二级标签 → 细分 → 证据
    c2_groups = defaultdict(list)
    for o in neg:
        c2_groups[o['cat2']].append(o)
    cat2_tree = []
    for cat2, items in sorted(c2_groups.items(), key=lambda x: -len(x[1])):
        sub = defaultdict(list)
        for o in items:
            sub[(o['cat3'] or '未指明（原文无具体落点）', o.get('cat3_desc', ''))].append(o)
        children = []
        for (mode, desc), its in sorted(sub.items(), key=lambda x: -len(x[1])):
            children.append(dict(
                key=mode, desc=desc, n=len(its),
                pct=round(len(its) / len(items) * 100, 2),
                ret=sum(1 for x in its if x['src'] == '买家之声退货报告'),
                rev=sum(1 for x in its if x['src'] != '买家之声退货报告'),
                quotes=pick_evidence(its, 4),
                all_quotes=uniq_evidence(its, 200)))
        cat2_tree.append(dict(
            cat1=items[0]['cat1'], cat2=cat2, n=len(items),
            pct_of_neg=round(len(items) / negN * 100, 2),
            ret=sum(1 for x in items if x['src'] == '买家之声退货报告'),
            rev=sum(1 for x in items if x['src'] != '买家之声退货报告'),
            subcats=children,
            all_quotes=uniq_evidence(items, 400)))

    # 一级大类汇总
    cat1_all = []
    for c1 in engine.CAT1_ORDER:
        n = sum(1 for o in ops if o['cat1'] == c1)
        if not n:
            continue
        cat1_all.append(dict(
            name=c1, n=n, pct=round(n / N * 100, 2),
            neg=sum(1 for o in ops if o['cat1'] == c1 and o['sentiment'] == '负面'),
            neu=sum(1 for o in ops if o['cat1'] == c1 and o['sentiment'] == '中性'),
            pos=sum(1 for o in ops if o['cat1'] == c1 and o['sentiment'] == '正向')))

    # 兼容旧模板：一级大类负面分布 + 负面二级树（按部件）
    cat1_neg = []
    for c1 in engine.CAT1_ORDER:
        n = sum(1 for o in neg if o['cat1'] == c1)
        if not n:
            continue
        cat1_neg.append(dict(name=c1, n=n, pct=round(n / negN * 100, 2)))

    neg_tree = []
    for d in dims:
        children = [dict(name=m['mode'], n=m['n'],
                         pct_in_cat1=m['pct_in_dim'],
                         pct_of_neg=m['pct_of_neg'],
                         quotes=m.get('quotes', []))
                    for m in d['modes']]
        neg_tree.append(dict(name=d['dim'], n=d['n'],
                             pct=round(d['n'] / negN * 100, 2),
                             children=children, quotes=[]))

    # 兼容旧模板：负面痛点 TopN（扁平）
    # 模板读 d.name / d.n / d.pct / d.cat1，这里统一成这套字段名
    # 「未指明（原文无具体落点）」不是失效模式，单独统计，不混入痛点排行
    neg_top = []
    unspec_total = 0
    for d in dims:
        for m in d['modes']:
            if m['mode'] == UNSPEC_LABEL:
                unspec_total += m['n']
                continue
            neg_top.append(dict(name=m['mode'], n=m['n'],
                                pct=round(m['pct_of_neg'], 2),
                                cat1=d['dim'], dim=d['dim'],
                                phen=m.get('phen', ''), quotes=m.get('quotes', [])))
    neg_top.sort(key=lambda x: -x['n'])
    neg_top = neg_top[:20]

    # 兼容旧模板：正向二级 Top
    pos_top = []
    for k, v in Counter(o['cat2'] for o in pos).most_common(10):
        pos_top.append(dict(name=k, n=v, pct=round(v / max(1, len(pos)) * 100, 2),
                            cat1='使用体验'))

    # 来源对比
    src_cmp = []
    for c1 in engine.CAT1_ORDER:
        rn = [o for o in neg if o['src'] == '买家之声退货报告' and o['cat1'] == c1]
        vn = [o for o in neg if o['src'] != '买家之声退货报告' and o['cat1'] == c1]
        if not rn and not vn:
            continue
        a = len(rn) / max(1, len([o for o in neg if o['src'] == '买家之声退货报告'])) * 100
        b = len(vn) / max(1, len([o for o in neg if o['src'] != '买家之声退货报告'])) * 100
        src_cmp.append(dict(name=c1, ret=round(a, 2), rev=round(b, 2),
                            diff=round(a - b, 2)))
    src_cmp.sort(key=lambda x: -x['ret'])

    # ---- 部件 × 模式 × 来源 交叉表 ----
    # 「普遍 vs 个案」判定依据：
    #   普遍问题 = 同一模式出现在 >=3 条不同原文，或同时出现在退货与评论两个来源
    #   个案问题 = 只在单一来源出现，且不同原文 <=2 条（偶发个例）
    CROSS_MIN_DOCS = 3
    cross_map = defaultdict(list)
    for o in neg:
        key = (o.get('part') or '未指明部件',
               o.get('cat3') or UNSPEC_LABEL,
               o.get('cat3_desc', ''))
        cross_map[key].append(o)

    cross = []
    for (part, mode, desc), items in cross_map.items():
        docs = len({o['raw'] for o in items})
        srcs = set(o['src'] for o in items)
        ret = sum(1 for x in items if x['src'] == '买家之声退货报告')
        rev = len(items) - ret
        both = len(srcs) > 1
        widespread = (docs >= CROSS_MIN_DOCS) or both
        cross.append(dict(
            part=part, mode=mode, desc=desc, n=len(items),
            docs=docs, ret=ret, rev=rev,
            pct=round(len(items) / negN * 100, 2),
            cross_source=both,
            kind='普遍' if widespread else '个案',
            quotes=pick_evidence(items, 3)))
    cross.sort(key=lambda x: (-x['n'], x['part'], x['mode']))

    # ---- 优先级排序 ----
    # 综合分 = 条数占比 + 跨来源加成 + 多原文加成
    for c in cross:
        c['score'] = round(
            c['pct'] * (1.0 + (0.5 if c['cross_source'] else 0.0)
                        + min(1.0, c['docs'] / 5.0) * 0.5), 3)
    # 「未指明（原文无具体落点）」不是失效模式，不进入行动清单，
    # 否则会把「原文没写清楚」排在真实痛点前面。
    priority = sorted([c for c in cross if c['mode'] != UNSPEC_LABEL],
                      key=lambda x: -x['score'])[:15]

    # ---- 按部件聚合的交叉汇总（部件 × 模式 是否跨来源）----
    part_cross = []
    part_groups = defaultdict(list)
    for c in cross:
        part_groups[c['part']].append(c)
    for part, cs in sorted(part_groups.items(), key=lambda x: -sum(c['n'] for c in x[1])):
        tot = sum(c['n'] for c in cs)
        part_cross.append(dict(
            part=part, n=tot,
            modes=len(cs),
            widespread=sum(1 for c in cs if c['kind'] == '普遍'),
            isolated=sum(1 for c in cs if c['kind'] == '个案'),
            cross_source=sum(1 for c in cs if c['cross_source']),
            ret=sum(c['ret'] for c in cs), rev=sum(c['rev'] for c in cs),
            top=sorted(cs, key=lambda x: -x['n'])[:3]))

    # 明细
    detail = []
    for i, o in enumerate(ops, 1):
        detail.append(dict(
            i=i, snip=o['snippet'], snip_zh=o.get('zh', ''),
            sent=o['sentiment'], src=o['src'],
            c1=o['cat1'], c2=o['cat2'], mode=o.get('cat3', ''),
            part=o.get('part', ''), spec=1 if o.get('concrete') else 0,
            doubt=1 if o.get('doubt') else 0,
            raw=o['raw'], raw_zh=o.get('raw_zh', '')))

    spec_n = sum(1 for o in ops if o.get('concrete'))
    ret_ops = [o for o in ops if o['src'] == '买家之声退货报告']
    rev_ops = [o for o in ops if o['src'] != '买家之声退货报告']
    kpi = dict(
        raw_total=len(all_rows), raw_ret=sum(1 for r in all_rows if r['src'] == '买家之声退货报告'),
        raw_rev=sum(1 for r in all_rows if r['src'] != '买家之声退货报告'),
        date=datetime.now().strftime('%Y-%m-%d'),
        total=N, negN=negN, pos=len(pos), neu=len(neu),
        neg_pct=round(len(neg) / N * 100, 2),
        pos_pct=round(len(pos) / N * 100, 2), neu_pct=round(len(neu) / N * 100, 2),
        spec=spec_n,
        spec_pct=round(spec_n / N * 100, 2),
        # 网页模板用的派生字段
        vague=N - spec_n,
        vague_pct=round((N - spec_n) / N * 100, 2),
        ret_op=len(ret_ops), rev_op=len(rev_ops),
        rev_pct=round(len(rev_ops) / N * 100, 2),
        ret_pct=round(len(ret_ops) / N * 100, 2),
        doubt=sum(1 for o in ops if o.get('doubt')),
        doubt_pct=round(sum(1 for o in ops if o.get('doubt')) / N * 100, 2),
        avg_per_text=round(N / max(1, len(all_rows)), 2),
        dim_count=len(dims),
        mode_count=sum(len(d['modes']) for d in dims),
        platform_cnt=sum(1 for o in ops if o.get('platform')),
        cat2_count=len(cat2_tree),
        cat2_sub_count=sum(len(t['subcats']) for t in cat2_tree),
    )

    data = dict(kpi=kpi, dims=dims, cat2_tree=cat2_tree, cat1_all=cat1_all,
                 cat1_neg=cat1_neg, neg_tree=neg_tree, neg_top=neg_top,
                 pos_top=pos_top, src_cmp=src_cmp, detail=detail, title=title,
                 cross=cross, part_cross=part_cross, priority=priority)

    # ---- 输出 ----
    os.makedirs(out_dir, exist_ok=True)
    base = re.sub(r'[\\/:*?"<>|]+', '_', title) or '洞察分析'
    html_path = os.path.join(out_dir, '%s_可视化.html' % base)
    xlsx_path = os.path.join(out_dir, '%s_洞察分析.xlsx' % base)
    md_path = os.path.join(out_dir, '%s_分析报告.md' % base)

    io_html.write(html_path, data, os.path.join(HERE, '..', 'templates', 'web'))
    io_excel.write(xlsx_path, data)
    io_md.write(md_path, data)

    print()
    print('原始文本 %d → 观点 %d（负面 %d / 中性 %d / 正向 %d）'
          % (len(all_rows), N, len(neg), len(neu), len(pos)))
    print('部件维度 %d，失效模式组合 %d，二级标签 %d'
          % (len(dims), kpi['mode_count'], len(cat2_tree)))
    print('输出：')
    for p in (html_path, xlsx_path, md_path):
        print('  ', p, '(%.1f KB)' % (os.path.getsize(p) / 1024))

    # ---- 审计 ----
    if audit:
        print('\n===== 抽样复核（%d 条）=====' % sample)
        random.seed(42)
        pool = [o for o in ops if o['snippet'].strip()]
        for o in random.sample(pool, min(sample, len(pool))):
            print('  %-64s -> %s / %s' % (o['snippet'][:64], o['cat1'], o['cat2']))
        uncls = [o for o in neg if UNSPEC_LABEL in o['cat2']
                 or UNSPEC_LABEL in (o.get('mode') or '')]
        print('\n未归类到具体部件/模式的负面观点：%d 条（%.1f%%）'
              % (len(uncls), len(uncls) / max(1, len(neg)) * 100))
        c = Counter(o['snippet'][:40] for o in uncls)
        for k, v in c.most_common(15):
            print('   %3d  %s' % (v, k))

    # ---- 质量门禁 ----
    # 不达标就明确失败，避免 Agent 跳过复核直接交付
    quality = assess_quality(ops, neg)
    print('\n===== 质量评估 =====')
    for k, v in quality['items']:
        print('  %-34s %s' % (k, v))
    kpi['quality'] = quality
    if strict and not quality['passed']:
        print('\n✗ 质量门禁未通过（--strict）：')
        for msg in quality['failures']:
            print('   - %s' % msg)
        print('\n请先修正 taxonomy 配置或补充译文，再重新运行。')
        raise SystemExit(3)
    if not quality['passed']:
        print('\n⚠ 质量未达标，建议加 --strict 强制门禁。当前问题：')
        for msg in quality['failures']:
            print('   - %s' % msg)
    return data


# 质量门禁阈值
STRICT_MAX_UNCLASSIFIED = 0.25   # 未归类负面占比上限
STRICT_MIN_TRANSLATION = 0.60    # 译文覆盖率下限
STRICT_MAX_MIXED = 0.15          # 中英混排占比上限


def assess_quality(ops, neg):
    """评估本次分析质量，返回可读指标 + 是否通过"""
    from translate import KEEP_EN
    n = len(ops)
    negN = len(neg) or 1

    uncls = [o for o in neg
             if UNSPEC_LABEL in o['cat2'] or UNSPEC_LABEL in (o.get('mode') or '')]
    uncls_pct = len(uncls) / negN * 100

    zh_ok = sum(1 for o in ops if o.get('zh'))
    zh_pct = zh_ok / max(1, n) * 100

    mixed = 0
    for o in ops:
        z = o.get('zh') or ''
        if not re.search(r'[\u4e00-\u9fff]', z):
            continue
        resid = [w for w in re.findall(r'[A-Za-z]{3,}', z)
                 if w.lower() not in KEEP_EN]
        if resid:
            mixed += 1
    mixed_pct = mixed / max(1, n) * 100

    # 部件/模式识别率：只在**非平台理由**的观点上统计
    # （平台理由本就是固定选项，没有部件与模式，用它做分母会失真）
    free_neg = [o for o in neg if not o.get('platform')]
    freeN = len(free_neg) or 1

    with_part = sum(1 for o in free_neg if o.get('part'))
    part_pct = with_part / freeN * 100

    with_mode = sum(1 for o in free_neg if (o.get('cat3') or o.get('mode'))
                    and UNSPEC_LABEL not in (o.get('cat3') or o.get('mode')))
    mode_pct = with_mode / freeN * 100

    failures = []
    if uncls_pct > STRICT_MAX_UNCLASSIFIED * 100:
        failures.append('未归类负面占比 %.1f%% > %.0f%%：需补 failure_modes 或 parts'
                        % (uncls_pct, STRICT_MAX_UNCLASSIFIED * 100))
    if zh_pct < STRICT_MIN_TRANSLATION * 100:
        failures.append('译文覆盖率 %.1f%% < %.0f%%：请用 --export-zh-todo 导出并让 Agent 翻译'
                        % (zh_pct, STRICT_MIN_TRANSLATION * 100))
    if mixed_pct > STRICT_MAX_MIXED * 100:
        failures.append('中英混排占比 %.1f%% > %.0f%%：译文需人工修正'
                        % (mixed_pct, STRICT_MAX_MIXED * 100))

    items = [
        ('未归类负面占比', '%.1f%%（%d/%d）' % (uncls_pct, len(uncls), negN)),
        ('命中具体失效模式', '%.1f%%（非平台理由 %d 条中）' % (mode_pct, freeN)),
        ('识别出具体部件', '%.1f%%' % part_pct),
        ('译文覆盖率', '%.1f%%' % zh_pct),
        ('中英混排占比', '%.1f%%' % mixed_pct),
        ('总观点数', '%d（其中平台理由 %d）' % (n, sum(1 for o in ops if o.get('platform')))),
    ]
    return dict(items=items, failures=failures, passed=not failures,
                uncls_pct=round(uncls_pct, 2), zh_pct=round(zh_pct, 2),
                mixed_pct=round(mixed_pct, 2), mode_pct=round(mode_pct, 2),
                part_pct=round(part_pct, 2))


def export_translation_todo(cfg_path, out_path):
    """导出待翻译清单（给 Agent 批量翻译）"""
    cfg = json.load(io.open(cfg_path, encoding='utf-8'))
    tax = Taxonomy(cfg)
    wbs = read_workbooks(cfg['inputs'])
    rows = []
    for wb in wbs:
        tc = pick_text_column(wb, cfg)
        if tc is None or _is_meta_sheet(wb, tc):
            continue
        rows.extend(extract_rows(wb, tc, pick_star_column(wb), pick_source_label(wb)))
    ops = split_opinions(rows, tax, '买家之声退货报告')
    items = [dict(en=o['snippet']) for o in ops]
    items += [dict(en=o['raw']) for o in ops if o['raw'] != o['snippet']]
    from translate import export_todo
    total, need = export_todo(items, out_path, cfg.get('extra_translations', {}))
    print('待译清单已写入：%s' % out_path)
    print('  唯一文本 %d 条，其中规则未覆盖需 Agent 翻译 %d 条' % (total, need))
    print('  → Agent 逐条填 zh 字段后，用 --zh <该文件> 回填')
    return total, need


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe', nargs='*', help='探查输入文件')
    ap.add_argument('--config', help='taxonomy 配置 json')
    ap.add_argument('--out-dir', default='./output')
    ap.add_argument('--title', default='亚马逊退货与评论洞察分析')
    ap.add_argument('--audit', action='store_true', help='抽样复核')
    ap.add_argument('--sample', type=int, default=60)
    ap.add_argument('--zh', help='译文 JSONL（Agent 翻译产出）')
    ap.add_argument('--export-zh-todo', help='导出待翻译清单到指定路径')
    ap.add_argument('--strict', action='store_true',
                    help='质量门禁：未归类占比超标时直接失败')
    a = ap.parse_args()

    if a.export_zh_todo:
        export_translation_todo(a.config, a.export_zh_todo)
        return
    if a.probe:
        probe(a.probe)
        return
    if not a.config:
        ap.print_help()
        return
    run(a.config, a.out_dir, a.title, a.audit, a.sample, a.zh, a.strict)


if __name__ == '__main__':
    main()
