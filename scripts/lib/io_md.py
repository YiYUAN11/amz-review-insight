# -*- coding: utf-8 -*-
"""生成 Markdown 分析报告"""
import io


def write(path, data):
    k = data['kpi']
    title = data.get('title', '亚马逊退货 & 评论洞察')
    L = []
    a = L.append

    a('# %s' % title)
    a('')
    a('**数据源**：买家之声退货报告 %d 条 + 商品买家评论 %d 条'
      % (k['raw_ret'], k['raw_rev']))
    a('**分类主线**：一级大类（%d）→ 二级标签（%d）→ 失效模式（%d 组）→ 买家原文'
      % (len(data['cat1_all']), k['cat2_count'], k['cat2_sub_count']))
    a('')
    a('---')
    a('')

    # 一、摘要
    a('## 一、整体摘要')
    a('')
    a('| 指标 | 数值 | 占比 |')
    a('|---|---:|---:|')
    a('| 原始文本 | %d | — |' % k['raw_total'])
    a('| 拆分后独立观点 | %d | 平均 %.2f 条/原文 |' % (k['total'], k['avg_per_text']))
    a('| 负面观点 | %d | %.2f%% |' % (k['negN'], k['neg_pct']))
    a('| 中性观点 | %d | %.2f%% |' % (k['neu'], k['neu_pct']))
    a('| 正向观点 | %d | %.2f%% |' % (k['pos'], k['pos_pct']))
    a('| 有明确具象点 | %d | %.2f%% |' % (k['spec'], k['spec_pct']))
    a('| 归类存疑 | %d | %.2f%% |' % (k['doubt'], k['doubt_pct']))
    a('| 部件维度 | %d 个 | — |' % k['dim_count'])
    a('| 二级标签 | %d 个 | — |' % k['cat2_count'])
    a('')
    a('> **口径**：**占本标签%%** 的分母是该二级标签内部条数；'
      '**占全部负面%%** 的分母是 %d 条。平台下拉理由 %d 条无具体落点，'
      '单独成列，不参与部件归因。'
      % (k['negN'], k['platform_cnt']))
    a('')

    # 二、一级大类
    a('---')
    a('')
    a('## 二、一级大类汇总（分母：全部观点 %d 条）' % k['total'])
    a('')
    a('| 一级大类 | 观点条数 | 占全部观点% | 负面 | 中性 | 正向 |')
    a('|---|---:|---:|---:|---:|---:|')
    for c in data['cat1_all']:
        a('| %s | %d | %.2f%% | %d | %d | %d |' % (
            c['name'], c['n'], c['pct'], c['neg'], c['neu'], c['pos']))
    a('')

    # 三、二级标签总览
    a('---')
    a('')
    a('## 三、二级标签总览（分母：全部负面 %d 条）' % k['negN'])
    a('')
    a('| 一级大类 | 二级标签 | 条数 | 占全部负面% | 细分数 | 最大细分模式 |')
    a('|---|---|---:|---:|---:|---|')
    for t in sorted(data['cat2_tree'], key=lambda x: -x['n']):
        subs = t['subcats']
        top = subs[0] if subs else None
        a('| %s | %s | %d | %.2f%% | %d | %s（%d） |' % (
            t['cat1'], t['cat2'], t['n'], t['pct_of_neg'], len(subs),
            top['key'] if top else '—', top['n'] if top else 0))
    a('')

    # 四、逐标签细分
    a('---')
    a('')
    a('## 四、逐二级标签细分（含中英对照原文）')
    a('')
    for t in data['cat2_tree']:
        a('### 【%s / %s】%d 条 · 占全部负面 %.2f%%' % (
            t['cat1'], t['cat2'], t['n'], t['pct_of_neg']))
        a('')
        a('| 细分（失效模式） | 具体现象 | 条数 | 占本标签% | 退货 | 评论 |')
        a('|---|---|---:|---:|---:|---:|')
        for s in t['subcats']:
            a('| **%s** | %s | %d | %.2f%% | %d | %d |' % (
                s['key'], (s.get('desc') or '').replace('|', '\\|'),
                s['n'], s['pct'], s['ret'], s['rev']))
        a('')
        any_q = False
        for s in t['subcats']:
            qs = s.get('quotes') or []
            if not qs:
                continue
            if not any_q:
                a('**买家原文证据（中英对照）：**')
                a('')
                any_q = True
            a('- **%s**（%d 条）' % (s['key'], s['n']))
            for q in qs:
                tag = '评论' if q['src'] != '买家之声退货报告' else '退货'
                a('  - **%s** 〔%s〕' % (q.get('zh') or '', tag))
                if q.get('t'):
                    a('    - 原文：`%s`' % q['t'].replace('`', ''))
            a('')

    # 五、来源差异
    a('---')
    a('')
    a('## 五、退货来源 vs 评论来源')
    a('')
    a('> 两边样本量悬殊，统一换算为「占该来源内部负面观点的百分比」再比较。')
    a('')
    a('| 一级大类 | 退货来源% | 评论来源% | 差值(pp) |')
    a('|---|---:|---:|---:|')
    for x in data['src_cmp']:
        a('| %s | %.2f%% | %.2f%% | %+.2f |' % (x['name'], x['ret'], x['rev'], x['diff']))
    a('')

    # 六、解读
    a('---')
    a('')
    a('## 六、业务解读')
    a('')
    top = []
    for d in data['dims']:
        for m in d['modes']:
            top.append((m['n'], m['pct_of_neg'], d['dim'], m['mode'], m.get('phen', '')))
    top.sort(reverse=True)
    a('### 6.1 最值得优先处理的 10 个失效模式')
    a('')
    a('| 排名 | 部件 | 失效模式 | 条数 | 占全部负面% |')
    a('|---|---|---|---:|---:|')
    for i, (n, pct, dim, mode, _) in enumerate(top[:10], 1):
        a('| %d | %s | %s | %d | %.2f%% |' % (i, dim, mode, n, pct))
    a('')
    a('### 6.2 样本局限')
    a('')
    a('- 评论仅 %d 条（占全部观点 %.2f%%），不足以代表整体口碑'
      % (k['raw_rev'], k['raw_rev'] / max(1, k['raw_total']) * 100))
    a('- 退货数据来自「已退货人群」，天然放大负面')
    a('- 平台下拉理由 %d 条（占负面 %.2f%%）无具体落点，未参与部件归因'
      % (k['platform_cnt'], k['platform_cnt'] / max(1, k['negN']) * 100))
    a('- 标注「未细分 / 归类存疑」的条目，是原文本身只写了 `doesn\'t fit`、`not working` '
      '这类无落点描述，如实单列，不做推测性归类')
    a('')
    a('---')
    a('')
    a('*全部 %d 条负面原文见 Excel「原文证据墙」工作表（中英对照）。*' % k['negN'])

    io.open(path, 'w', encoding='utf-8').write('\n'.join(L))
    return path
