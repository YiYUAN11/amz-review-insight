# -*- coding: utf-8 -*-
"""校验生成的网页：提取内嵌数据并检查结构"""
import io, json, re, sys

path = sys.argv[1]
s = io.open(path, encoding='utf-8').read()

# 外链检查
ext = re.findall(r'<(?:script src|link[^>]*href)="([^"]+)"', s)
print('外部引用：%s' % (ext if ext else '无'))

# 提取数据
m = re.search(r'window\.__INSIGHT_DATA__\s*=\s*', s)
if not m:
    print('!! 找不到数据注入')
    sys.exit(1)
start = m.end()
depth = 0
for i in range(start, len(s)):
    if s[i] == '{':
        depth += 1
    elif s[i] == '}':
        depth -= 1
        if depth == 0:
            end = i + 1
            break
data = json.loads(s[start:end])

print('顶层键：%s' % sorted(data.keys()))
d0 = data['dims'][0]
print('dims[0]：%s' % sorted(d0.keys()))
print('  modes[0]：%s' % sorted(d0['modes'][0].keys()))
c0 = data['cat2_tree'][0]
print('cat2_tree[0]：%s' % sorted(c0.keys()))
print('  subcats[0]：%s' % sorted(c0['subcats'][0].keys()))
print('  all_quotes[0]：%s' % sorted(c0['all_quotes'][0].keys()))
print('  quotes[0]：%s' % (sorted(c0['subcats'][0]['quotes'][0].keys())
                          if c0['subcats'][0].get('quotes') else '无'))
print('  subcats 类型：%s' % type(c0['subcats']).__name__)
print('detail[0]：%s' % sorted(data['detail'][0].keys()))
