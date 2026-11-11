# -*- coding: utf-8 -*-
"""生成单文件可视化网页（白天主题 / 中英对照）"""
import io
import json
import os
import shutil

TPL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates', 'web')


def write(out_path, data, tpl_dir=TPL):
    html = io.open(os.path.join(tpl_dir, 'index.html'), encoding='utf-8').read()
    css_files = ['styles.css', 'drill.css', 'v2.css', 'c2.css']
    js_files = ['app.js', 'v2.js', 'c2.js']

    css_all = []
    for f in css_files:
        p = os.path.join(tpl_dir, f)
        if os.path.exists(p):
            css_all.append('/* ===== %s ===== */\n' % f + io.open(p, encoding='utf-8').read())
    js_all = []
    for f in js_files:
        p = os.path.join(tpl_dir, f)
        if os.path.exists(p):
            js_all.append('/* ===== %s ===== */\n' % f + io.open(p, encoding='utf-8').read())

    # 标题与副标题
    k = data['kpi']
    html = html.replace('<h1>亚马逊退货 &amp; 评论 <span class="accent">洞察分析</span></h1>',
                        '<h1>%s <span class="accent">洞察分析</span></h1>'
                        % _esc(data.get('title', '亚马逊退货 & 评论')))
    html = html.replace('<span id="m-raw">—</span>',
                        '<span id="m-raw">%s</span>' % _num(k['raw_total']))
    html = html.replace('<span id="m-total">—</span>',
                        '<span id="m-total">%s</span>' % _num(k['total']))

    # 去掉外部引用
    for f in css_files:
        html = html.replace('<link rel="stylesheet" href="%s">' % f, '')
    html = html.replace('</head>', '<style>\n' + '\n'.join(css_all) + '\n</style>\n</head>')
    for f in js_files + ['data.js']:
        html = html.replace('<script src="%s"></script>' % f, '')
    # 内联 JSON 必须转义 < > &：买家原文若含 </script> 会提前闭合脚本块，
    # 直接执行注入的 HTML/JS（XSS）。转成 \u 形式后 JSON.parse 解码结果不变。
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    payload = (payload.replace('&', '\\u0026')
                      .replace('<', '\\u003c')
                      .replace('>', '\\u003e'))
    payload = 'window.__INSIGHT_DATA__ = ' + payload + ';\n'
    assert '</script' not in payload.lower(), '内联数据未正确转义（存在 </script）'
    html = html.replace('</body>', '<script>\n' + payload + '\n' +
                        '\n'.join(js_all) + '\n</script>\n</body>')
    # 校验：不能残留任何外部引用
    for f in css_files + js_files + ['data.js']:
        assert ('href="%s"' % f) not in html, 'CSS 未内联: %s' % f
        assert ('src="%s"' % f) not in html, 'JS 未内联: %s' % f
    assert '__INSIGHT_DATA__' in html, '数据缺失'
    io.open(out_path, 'w', encoding='utf-8').write(html)
    return out_path


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _num(n):
    return format(n, ',')
