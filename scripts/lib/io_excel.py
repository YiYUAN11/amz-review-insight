# -*- coding: utf-8 -*-
"""生成 Excel：二级标签细分 + 维度总览 + 原文证据墙"""
import io

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

HDR = PatternFill('solid', fgColor='1F4E79')
HF = Font(color='FFFFFF', bold=True, size=11)
TITLE = Font(bold=True, size=14, color='1F4E79')
SUB = PatternFill('solid', fgColor='EAF1FE')
THIN = Side(style='thin', color='DDE3EC')
BD = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def write(path, data):
    k = data['kpi']
    title = data.get('title', '洞察分析')
    wb = Workbook()

    # ============ Sheet1：二级标签 → 细分 ============
    ws = wb.active
    ws.title = '二级标签细分'
    ws['A1'] = '%s —— 二级标签 → 细分 → 买家原文' % title
    ws['A1'].font = TITLE
    ws['A2'] = ('以二级标签为主线，按「失效模式」拆到具体表现，并附中英对照原文。'
                '分母：占本标签% 为该二级标签内部条数。')
    ws['A2'].font = Font(size=9, color='5A687C')

    hdr = ['一级大类', '二级标签', '细分（失效模式）', '具体现象', '条数',
           '占本标签%', '退货来源', '评论来源', '中文', '英文原文1', '英文原文2',
           '英文原文3', '英文原文4']
    for j, h in enumerate(hdr, start=1):
        c = ws.cell(row=4, column=j, value=h)
        c.fill = HDR
        c.font = HF
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = BD
    r = 5
    for t in data['cat2_tree']:
        first = True
        for s in t['subcats']:
            qs = s.get('quotes') or []
            ws.cell(row=r, column=1, value=t['cat1'] if first else '')
            ws.cell(row=r, column=2, value=t['cat2'] if first else '')
            ws.cell(row=r, column=3, value=s['key'])
            ws.cell(row=r, column=4, value=s.get('desc') or '')
            ws.cell(row=r, column=5, value=s['n'])
            ws.cell(row=r, column=6, value=s['pct']).number_format = '0.00"%"'
            ws.cell(row=r, column=7, value=s['ret'])
            ws.cell(row=r, column=8, value=s['rev'])
            for qi in range(4):
                if qi < len(qs):
                    ws.cell(row=r, column=9 + qi, value=qs[qi].get('zh', ''))
            for j in range(1, 14):
                cell = ws.cell(row=r, column=j)
                cell.border = BD
                cell.alignment = Alignment(vertical='top',
                                           wrap_text=(j in (2, 3, 4, 9, 10, 11, 12, 13)))
            first = False
            r += 1
        ws.cell(row=r, column=2, value='小计 · ' + t['cat2'])
        ws.cell(row=r, column=5, value=t['n'])
        ws.cell(row=r, column=6, value=100.0).number_format = '0.00"%"'
        for j in range(1, 14):
            c = ws.cell(row=r, column=j)
            c.fill = SUB
            c.font = Font(bold=True)
            c.border = BD
        r += 1
    for col, w in {'A': 15, 'B': 26, 'C': 16, 'D': 40, 'E': 8, 'F': 11,
                   'G': 9, 'H': 9, 'I': 30, 'J': 40, 'K': 40, 'L': 40, 'M': 40}.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = 'A5'

    # ============ Sheet2：二级标签总览 ============
    ws2 = wb.create_sheet('二级标签总览')
    ws2['A1'] = '二级标签总览（按条数降序）'
    ws2['A1'].font = TITLE
    h2 = ['一级大类', '二级标签', '负面条数', '占全部负面%', '退货', '评论',
          '细分数', '最大细分模式', '最大模式条数']
    for j, h in enumerate(h2, start=1):
        c = ws2.cell(row=3, column=j, value=h)
        c.fill = HDR
        c.font = HF
        c.alignment = Alignment(horizontal='center', wrap_text=True)
        c.border = BD
    r = 4
    for t in sorted(data['cat2_tree'], key=lambda x: -x['n']):
        subs = t['subcats']
        top = subs[0] if subs else None
        vals = [t['cat1'], t['cat2'], t['n'], t['pct_of_neg'], t['ret'], t['rev'],
                len(subs), top['key'] if top else '', top['n'] if top else 0]
        for j, v in enumerate(vals, start=1):
            cell = ws2.cell(row=r, column=j, value=v)
            cell.border = BD
            if j == 4:
                cell.number_format = '0.00"%"'
        r += 1
    for col, w in {'A': 15, 'B': 28, 'C': 10, 'D': 13, 'E': 8, 'F': 8,
                   'G': 10, 'H': 20, 'I': 13}.items():
        ws2.column_dimensions[col].width = w
    ws2.freeze_panes = 'A4'

    # ============ Sheet3：部件维度 → 失效模式 ============
    ws3 = wb.create_sheet('部件维度×失效模式')
    ws3['A1'] = '部件维度 → 失效模式（含现象描述与原文）'
    ws3['A1'].font = TITLE
    h3 = ['部件维度', '失效模式', '具体现象', '条数', '占本维度%', '占全部负面%',
          '退货', '评论', '中文证据', '英文证据']
    for j, h in enumerate(h3, start=1):
        c = ws3.cell(row=3, column=j, value=h)
        c.fill = HDR
        c.font = HF
        c.alignment = Alignment(horizontal='center', wrap_text=True)
        c.border = BD
    r = 4
    for d in data['dims']:
        first = True
        for m in d['modes']:
            qs = m.get('quotes') or []
            ws3.cell(row=r, column=1, value=d['dim'] if first else '')
            ws3.cell(row=r, column=2, value=m['mode'])
            ws3.cell(row=r, column=3, value=m.get('phen') or '')
            ws3.cell(row=r, column=4, value=m['n'])
            ws3.cell(row=r, column=5, value=m['pct_in_dim']).number_format = '0.00"%"'
            ws3.cell(row=r, column=6, value=m['pct_of_neg']).number_format = '0.00"%"'
            ws3.cell(row=r, column=7, value=m['ret'])
            ws3.cell(row=r, column=8, value=m['rev'])
            if qs:
                ws3.cell(row=r, column=9, value=qs[0].get('zh', ''))
                ws3.cell(row=r, column=10, value=qs[0].get('t', ''))
            for j in range(1, 11):
                cell = ws3.cell(row=r, column=j)
                cell.border = BD
                cell.alignment = Alignment(vertical='top', wrap_text=(j in (2, 3, 9, 10)))
            first = False
            r += 1
    for col, w in {'A': 16, 'B': 18, 'C': 42, 'D': 8, 'E': 11, 'F': 12,
                   'G': 8, 'H': 8, 'I': 32, 'J': 44}.items():
        ws3.column_dimensions[col].width = w
    ws3.freeze_panes = 'A4'

    # ============ Sheet4：全部原文证据墙 ============
    ws4 = wb.create_sheet('原文证据墙')
    ws4['A1'] = '全部负面原文 · 按二级标签归类（中英对照）'
    ws4['A1'].font = TITLE
    h4 = ['序号', '一级大类', '二级标签', '失效模式', '中文译文', '英文原文', '来源']
    for j, h in enumerate(h4, start=1):
        c = ws4.cell(row=3, column=j, value=h)
        c.fill = HDR
        c.font = HF
        c.alignment = Alignment(horizontal='center', wrap_text=True)
        c.border = BD
    negs = [d for d in data['detail'] if d['sent'] == '负面']
    c2order = {t['cat2']: i for i, t in
                enumerate(sorted(data['cat2_tree'], key=lambda x: -x['n']))}
    negs.sort(key=lambda o: (c2order.get(o['c2'], 999), -len(o['snip'])))
    r = 4
    for i, o in enumerate(negs, 1):
        vals = [i, o['c1'], o['c2'], o.get('mode', ''), o.get('snip_zh', ''),
                o['snip'], '退货报告' if o['src'] == '买家之声退货报告' else '买家评论']
        for j, v in enumerate(vals, start=1):
            cell = ws4.cell(row=r, column=j, value=v)
            cell.border = BD
            cell.alignment = Alignment(vertical='top', wrap_text=(j in (5, 6)))
        r += 1
    for col, w in {'A': 7, 'B': 15, 'C': 26, 'D': 16, 'E': 40, 'F': 60, 'G': 11}.items():
        ws4.column_dimensions[col].width = w
    ws4.freeze_panes = 'A4'

    # ============ Sheet5：全部观点明细 ============
    ws5 = wb.create_sheet('全量观点明细')
    ws5['A1'] = '全部 %d 条独立观点明细' % k['total']
    ws5['A1'].font = TITLE
    h5 = ['序号', '原文片段', '中文译文', '情感', '来源', '一级分类', '二级标签',
          '失效模式', '部件', '有具象点', '归类存疑', '英文原文全文', '原文全文(中文)']
    for j, h in enumerate(h5, start=1):
        c = ws5.cell(row=3, column=j, value=h)
        c.fill = HDR
        c.font = HF
        c.alignment = Alignment(horizontal='center', wrap_text=True)
        c.border = BD
    r = 4
    for o in data['detail']:
        vals = [o['i'], o['snip'], o.get('snip_zh', ''), o['sent'],
                '退货报告' if o['src'] == '买家之声退货报告' else '买家评论',
                o['c1'], o['c2'], o.get('mode', ''), o.get('part', ''),
                '有' if o['spec'] else '无', '存疑' if o['doubt'] else '',
                o.get('raw', ''), o.get('raw_zh', '')]
        for j, v in enumerate(vals, start=1):
            cell = ws5.cell(row=r, column=j, value=v)
            cell.border = BD
            cell.alignment = Alignment(vertical='top', wrap_text=(j in (2, 3, 12, 13)))
        r += 1
    for col, w in {'A': 7, 'B': 46, 'C': 40, 'D': 8, 'E': 11, 'F': 15, 'G': 24,
                   'H': 16, 'I': 13, 'J': 9, 'K': 9, 'L': 56, 'M': 56}.items():
        ws5.column_dimensions[col].width = w
    ws5.freeze_panes = 'A4'

    # ============ Sheet6：部件 × 模式 × 来源 交叉表 ============
    ws6 = wb.create_sheet('交叉表_部件×模式×来源')
    ws6['A1'] = '部件 × 失效模式 × 来源 交叉表（含「普遍 vs 个案」判定）'
    ws6['A1'].font = TITLE
    ws6['A2'] = ('判定口径：**普遍** = 同一模式出现在 ≥3 条不同买家原文，'
                 '或同时出现在退货报告与买家评论两个来源；'
                 '**个案** = 单一来源且不同原文 ≤2 条（偶发个例）。'
                 '优先级综合分 = 条数占比 × (1 + 跨来源加成 0.5 + 多原文加成)。')
    ws6['A2'].font = Font(size=9, color='5A687C')
    h6 = ['部件', '失效模式', '具体现象', '条数', '占全部负面%',
          '涉及原文数', '退货', '评论', '跨来源', '判定', '优先级分',
          '中文证据', '英文证据']
    for j, h in enumerate(h6, start=1):
        c = ws6.cell(row=4, column=j, value=h)
        c.fill = HDR
        c.font = HF
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = BD
    r = 5
    for x in data.get('cross', []):
        qs = x.get('quotes') or []
        vals = [x['part'], x['mode'], x.get('desc') or '', x['n'], x['pct'],
                x['docs'], x['ret'], x['rev'],
                '是' if x['cross_source'] else '否', x['kind'],
                x.get('score', 0)]
        for j, v in enumerate(vals, start=1):
            cell = ws6.cell(row=r, column=j, value=v)
            cell.border = BD
            cell.alignment = Alignment(vertical='top', wrap_text=(j in (2, 3, 12, 13)))
        if x['kind'] == '普遍':
            ws6.cell(row=r, column=10).fill = PatternFill('solid', fgColor='FCE4E4')
            ws6.cell(row=r, column=10).font = Font(bold=True, color='B42318')
        else:
            ws6.cell(row=r, column=10).fill = PatternFill('solid', fgColor='E8F0FE')
            ws6.cell(row=r, column=10).font = Font(color='1F4E79')
        if qs:
            ws6.cell(row=r, column=12, value=qs[0].get('zh', ''))
            ws6.cell(row=r, column=13, value=qs[0].get('t', ''))
        r += 1
    for col, w in {'A': 15, 'B': 18, 'C': 38, 'D': 7, 'E': 12, 'F': 10,
                   'G': 7, 'H': 7, 'I': 9, 'J': 8, 'K': 10,
                   'L': 30, 'M': 44}.items():
        ws6.column_dimensions[col].width = w
    ws6.freeze_panes = 'A5'

    # ============ Sheet7：优先级行动清单 ============
    ws7 = wb.create_sheet('优先级行动清单')
    ws7['A1'] = '优先级行动清单（Top 15，含普遍/个案判定）'
    ws7['A1'].font = TITLE
    ws7['A2'] = ('综合分 = 条数占比 × (1 + 跨来源加成 0.5 + 多原文加成)。'
                 '同一问题同时出现在退货与评论两个来源时，优先级更高。')
    ws7['A2'].font = Font(size=9, color='5A687C')
    h7 = ['优先级', '部件', '失效模式', '条数', '占全部负面%', '涉及原文数',
          '跨来源', '判定', '综合分', '建议动作', '中文证据', '英文证据']
    for j, h in enumerate(h7, start=1):
        c = ws7.cell(row=4, column=j, value=h)
        c.fill = HDR
        c.font = HF
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = BD
    r = 5
    for i, x in enumerate(data.get('priority', []), 1):
        qs = x.get('quotes') or []
        if x['cross_source']:
            action = '优先立项：退货与评论双来源共现，属结构性问题'
        elif x['kind'] == '普遍':
            action = '列入改进：单一来源但多买家共现，需产品侧确认'
        else:
            action = '观察项：偶发个例，先收集更多样本再判断'
        vals = [i, x['part'], x['mode'], x['n'], x['pct'], x['docs'],
                '是' if x['cross_source'] else '否', x['kind'],
                x.get('score', 0), action]
        for j, v in enumerate(vals, start=1):
            cell = ws7.cell(row=r, column=j, value=v)
            cell.border = BD
            cell.alignment = Alignment(vertical='top', wrap_text=(j in (2, 3, 10, 11, 12)))
        if qs:
            ws7.cell(row=r, column=11, value=qs[0].get('zh', ''))
            ws7.cell(row=r, column=12, value=qs[0].get('t', ''))
        r += 1
    for col, w in {'A': 8, 'B': 15, 'C': 18, 'D': 7, 'E': 12, 'F': 10,
                   'G': 9, 'H': 8, 'I': 10, 'J': 40, 'K': 30, 'L': 44}.items():
        ws7.column_dimensions[col].width = w
    ws7.freeze_panes = 'A5'

    wb.save(path)
    return path
