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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'lib'))
sys.path.insert(0, HERE)

import engine
from engine import Taxonomy, split_opinions, build_stats, normalize, norm_key
from translate import Translator
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
    from discover import pick_text_col
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
def run(cfg_path, out_dir, title, audit=False, sample=60):
    cfg = json.load(io.open(cfg_path, encoding='utf-8'))
    tax = Taxonomy(cfg)
    tr = Translator(cfg.get('extra_translations', {}))

    wbs = read_workbooks(cfg['inputs'])
    all_rows = []
    for wb in wbs:
        tc = pick_text_column(wb, cfg)
        if tc is None:
            print('  · %s/%s  未识别到反馈文本列，跳过' % (wb['file'], wb['sheet']))
            continue
        # 打印识别依据，便于人工核验
        from discover import explain_pick
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
    for o in ops:
        o['zh'] = tr(o['snippet'])
        o['raw_zh'] = tr(o['raw'])

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
        dim_groups[o.get('part') or '未指明部件'][(o['cat3'] or '未细分',
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
            sub[(o['cat3'] or '未细分', o.get('cat3_desc', ''))].append(o)
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
    neg_top = []
    for d in dims:
        for m in d['modes']:
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

    kpi = dict(
        raw_total=len(all_rows), raw_ret=sum(1 for r in all_rows if r['src'] == '买家之声退货报告'),
        raw_rev=sum(1 for r in all_rows if r['src'] != '买家之声退货报告'),
        total=N, negN=negN, pos=len(pos), neu=len(neu),
        neg_pct=round(len(neg) / N * 100, 2),
        pos_pct=round(len(pos) / N * 100, 2), neu_pct=round(len(neu) / N * 100, 2),
        spec=sum(1 for o in ops if o.get('concrete')),
        spec_pct=round(sum(1 for o in ops if o.get('concrete')) / N * 100, 2),
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
                 pos_top=pos_top, src_cmp=src_cmp, detail=detail, title=title)

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
        uncls = [o for o in neg if o['cat2'].endswith('（未细分）')
                 or o['cat2'] == '其他（未细分）']
        print('\n未归类到具体部件/模式的负面观点：%d 条（%.1f%%）'
              % (len(uncls), len(uncls) / max(1, len(neg)) * 100))
        c = Counter(o['snippet'][:40] for o in uncls)
        for k, v in c.most_common(15):
            print('   %3d  %s' % (v, k))
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe', nargs='*', help='探查输入文件')
    ap.add_argument('--config', help='taxonomy 配置 json')
    ap.add_argument('--out-dir', default='./output')
    ap.add_argument('--title', default='亚马逊退货与评论洞察分析')
    ap.add_argument('--audit', action='store_true', help='抽样复核')
    ap.add_argument('--sample', type=int, default=60)
    a = ap.parse_args()

    if a.probe:
        probe(a.probe)
        return
    if not a.config:
        ap.print_help()
        return
    run(a.config, a.out_dir, a.title, a.audit, a.sample)


if __name__ == '__main__':
    main()
