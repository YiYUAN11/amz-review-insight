# -*- coding: utf-8 -*-
"""
taxonomy 配置自检 —— 跑全流程前先验证配置本身是否自洽。

用法：
    python scripts/validate_taxonomy.py --config taxonomy.json
    python scripts/validate_taxonomy.py --config taxonomy.json --strict

配置结构（与 engine.py 的 Taxonomy 一致）：
    parts        : [{name, aliases[], cat1, modes[]}]
    failure_modes: [{name, desc, cat1, patterns[]}]   ← 正则写在 patterns 里
    global_modes : ["模式名", ...]                     ← 只是名字列表
    mode_cat1    : {模式名: 一级大类}

检查项：
  1. 结构完整性：必填字段、parts/failure_modes 格式
  2. 引用完整性：parts[].modes / global_modes 引用的模式名是否存在（静默失效高发点）
  3. 模式归类：failure_modes[].cat1 是否是 9 类固定一级大类之一
  4. 正则可编译：所有 patterns 能否被 re 编译
  5. 命中率预检：跑一小段语料，看模式/部件的命中率
  6. 重复检测：同名部件、同名模式、重复正则

退出码：0 = 通过；1 = 有 ERROR（--strict 下 WARN 也会返回 1）
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'lib'))

from engine import CAT1_ORDER, UNSPEC_LABEL  # noqa: E402

ERRORS = []
WARNS = []
INFO = []


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNS.append(msg)


def info(msg):
    INFO.append(msg)


def _rx_list(m):
    """兼容 patterns / rx 两种写法"""
    rx = m.get('patterns')
    if rx is None:
        rx = m.get('rx')
    if isinstance(rx, str):
        rx = [rx]
    return rx or []


def check_structure(cfg):
    """1. 结构完整性"""
    for key in ('parts', 'failure_modes', 'inputs'):
        if key not in cfg:
            err('缺少必填字段：%s' % key)
    if not isinstance(cfg.get('parts'), list) or not cfg['parts']:
        err('parts 必须是非空数组')
    if not isinstance(cfg.get('failure_modes'), list) or not cfg['failure_modes']:
        err('failure_modes 必须是非空数组')
    if not isinstance(cfg.get('inputs'), list) or not cfg['inputs']:
        err('inputs 必须是非空数组（待分析文件路径）')
    for p in cfg.get('inputs', []):
        if not os.path.exists(p):
            warn('inputs 中的文件不存在：%s' % p)


def check_parts(cfg):
    """2. parts 内部一致性"""
    names = []
    for i, p in enumerate(cfg.get('parts', [])):
        tag = 'parts[%d] %s' % (i, p.get('name', '?'))
        if not isinstance(p, dict):
            err('%s 不是对象' % tag)
            continue
        if not p.get('name'):
            err('%s 缺少 name' % tag)
            continue
        names.append(p['name'])
        if not p.get('aliases'):
            warn('%s 没有 aliases，买家常用别名可能匹配不到' % tag)
        cat1 = p.get('cat1')
        if cat1 and cat1 not in CAT1_ORDER:
            err('%s 的 cat1 = "%s" 不在 9 类固定一级大类里' % (tag, cat1))
        for a in p.get('aliases', []):
            if not isinstance(a, str):
                err('%s 的 aliases 里有非字符串项' % tag)
    dup = [n for n in set(names) if names.count(n) > 1]
    if dup:
        err('parts 有重名部件：%s' % '、'.join(dup))


def check_modes(cfg):
    """3. failure_modes 一致性，返回全部模式名集合"""
    mode_names = []
    for i, m in enumerate(cfg.get('failure_modes', [])):
        tag = 'failure_modes[%d] %s' % (i, m.get('name', '?'))
        if not isinstance(m, dict):
            err('%s 不是对象' % tag)
            continue
        if not m.get('name'):
            err('%s 缺少 name' % tag)
            continue
        mode_names.append(m['name'])
        cat1 = m.get('cat1')
        if not cat1:
            err('%s 缺少 cat1（该模式归到哪个一级大类）' % tag)
        elif cat1 not in CAT1_ORDER:
            err('%s 的 cat1 = "%s" 不在 9 类固定一级大类里' % (tag, cat1))
        if not m.get('desc'):
            warn('%s 没有 desc（现象描述），Excel 该列会留空' % tag)
        rx = _rx_list(m)
        if not rx:
            warn('%s 没有 patterns，不会被匹配到' % tag)
        for r in rx:
            if not isinstance(r, str):
                err('%s 的 patterns 里有非字符串项' % tag)
                continue
            try:
                re.compile(r)
            except re.error as e:
                err('%s 的 patterns 无法编译：%s → %s' % (tag, r, e))
    dup = [n for n in set(mode_names) if mode_names.count(n) > 1]
    if dup:
        err('failure_modes 里有重名模式：%s' % '、'.join(dup))
    return set(mode_names)


def check_mode_refs(cfg, all_modes):
    """4. parts[].modes / global_modes 引用的模式是否存在"""
    for p in cfg.get('parts', []):
        if not isinstance(p, dict):
            continue
        for m in p.get('modes', []) or []:
            if m not in all_modes:
                err('部件「%s」的 modes 引用了不存在的模式「%s」'
                    '（会被静默忽略：不报错，但也永远匹配不上）'
                    % (p.get('name'), m))
    gm = cfg.get('global_modes') or []
    if isinstance(gm, dict):
        gm = list(gm.keys())
    if not isinstance(gm, list):
        err('global_modes 必须是模式名数组（当前是 %s）' % type(gm).__name__)
        gm = []
    for m in gm:
        if m not in all_modes:
            err('global_modes 引用了不存在的模式「%s」' % m)
    for name, c1 in (cfg.get('mode_cat1') or {}).items():
        if name not in all_modes:
            warn('mode_cat1 引用了不存在的模式「%s」' % name)
        if c1 not in CAT1_ORDER:
            err('mode_cat1["%s"] = "%s" 不是合法一级大类' % (name, c1))


def check_regex_dup(cfg):
    """5. 重复正则检查
    引擎按 failure_modes 数组顺序匹配，先声明的赢。
    因此：
      · 某模式若**所有** patterns 都被前面的模式覆盖 → 它永远不会被命中（真问题，ERROR）
      · 部分重叠 → 只是「后者被前者遮蔽」，提示即可
    同属一个一级大类的重叠属于同类细分，合并成一条提示。
    """
    seen = {}
    pairs = {}
    shadowed = {}   # 模式名 -> 被完全遮蔽的 patterns 数
    total = {}
    cat1_of = {}
    for m in cfg.get('failure_modes', []):
        if not isinstance(m, dict):
            continue
        name = m.get('name')
        cat1_of[name] = m.get('cat1')
        for r in _rx_list(m):
            key = re.sub(r'\s+', '', r.lower())
            total[name] = total.get(name, 0) + 1
            if key in seen and seen[key] != name:
                pair = tuple(sorted([seen[key], name]))
                pairs.setdefault(pair, []).append(r)
                shadowed[name] = shadowed.get(name, 0) + 1
            seen[key] = name

    for name, c in sorted(shadowed.items()):
        if c >= total.get(name, 0):
            err('模式「%s」的 %d 条 patterns 全部被更早声明的模式覆盖，'
                '它永远不会被命中（请改写成互斥的正则，或删除该模式）'
                % (name, c))

    same_family = []
    cross_family = []
    for (a, b), rs in sorted(pairs.items()):
        if cat1_of.get(a) and cat1_of.get(a) == cat1_of.get(b):
            same_family.append((a, b, rs))
        else:
            cross_family.append((a, b, rs))

    if same_family:
        info('同类细分重叠 %d 对（同一一级大类内，先声明的优先，不影响结论）：'
             % len(same_family))
        for a, b, rs in same_family:
            info('  · %s / %s 共用 %d 条（例：%s）'
                 % (a, b, len(rs), rs[0][:50]))
    if cross_family:
        warn('跨类重叠 %d 对（不同一级大类共用同一正则，可能归错类）：'
             % len(cross_family))
        for a, b, rs in cross_family:
            warn('  · 「%s」与「%s」共用 %d 条 patterns，先声明的赢（例：%s）'
                 % (a, b, len(rs), rs[0][:50]))


def check_hit_rate(cfg):
    """6. 命中率预检（用真实语料抽样）"""
    try:
        from run import (read_workbooks, pick_text_column, pick_star_column,
                         pick_source_label, extract_rows, _is_meta_sheet)
        from engine import Taxonomy, split_opinions
    except Exception as e:  # pragma: no cover
        warn('无法导入引擎，跳过命中率预检：%s' % e)
        return
    inputs = [p for p in cfg.get('inputs', []) if os.path.exists(p)]
    if not inputs:
        warn('没有可用的输入文件，跳过命中率预检')
        return
    try:
        tax = Taxonomy(cfg)
    except Exception as e:
        err('Taxonomy 构造失败：%s' % e)
        return
    rows = []
    try:
        for wb in read_workbooks(inputs):
            tc = pick_text_column(wb, cfg)
            if tc is None or _is_meta_sheet(wb, tc):
                continue
            rows.extend(extract_rows(wb, tc, pick_star_column(wb),
                                     pick_source_label(wb)))
    except Exception as e:
        err('读取输入文件失败：%s' % e)
        return
    if not rows:
        warn('输入文件里没有识别到反馈文本行')
        return
    ops = split_opinions(rows, tax, '预检')
    neg = [o for o in ops if o['sentiment'] == '负面']
    free = [o for o in neg if not o.get('platform')]
    if not free:
        warn('没有非平台理由的负面观点，跳过命中率预检')
        return
    with_mode = sum(1 for o in free
                    if (o.get('cat3') or '') and UNSPEC_LABEL not in o['cat3'])
    with_part = sum(1 for o in free if o.get('part'))
    info('预检样本：%d 条原文 → %d 条观点（负面 %d，其中非平台理由 %d）'
         % (len(rows), len(ops), len(neg), len(free)))
    info('  命中具体失效模式：%.1f%%' % (with_mode / len(free) * 100))
    info('  识别出具体部件：%.1f%%' % (with_part / len(free) * 100))
    if with_mode / len(free) < 0.40:
        warn('模式命中率偏低（<40%），建议补充 failure_modes 的 patterns 覆盖')
    if with_part / len(free) < 0.50:
        warn('部件识别率偏低（<50%），建议补充 parts 的 aliases')


def check_translation(cfg):
    """7. 翻译词典自检"""
    try:
        from dict_zh import PHRASES, WORDS
        from translate import rule_translate
    except Exception as e:
        warn('无法导入词典：%s' % e)
        return
    info('词典规模：%d 条短语 / %d 个词' % (len(PHRASES), len(WORDS)))
    extra = cfg.get('extra_translations') or {}
    if extra:
        info('extra_translations：%d 条品类专属词' % len(extra))
    for t in ('the kickstand is great', 'the hinge broke', 'does not fit'):
        try:
            z = rule_translate(t, extra)
        except Exception as e:
            err('规则翻译调用失败：%s → %s' % (t, e))
            continue
        if not z:
            warn('规则翻译未命中：%s' % t)


def main():
    ap = argparse.ArgumentParser(description='taxonomy 配置自检')
    ap.add_argument('--config', required=True)
    ap.add_argument('--strict', action='store_true',
                    help='有 WARN 也返回非 0 退出码')
    args = ap.parse_args()

    if not os.path.exists(args.config):
        print('配置文件不存在：%s' % args.config)
        return 1
    with io.open(args.config, encoding='utf-8') as f:
        cfg = json.load(f)

    print('=' * 64)
    print('taxonomy 配置自检：%s' % args.config)
    print('=' * 64)

    check_structure(cfg)
    check_parts(cfg)
    all_modes = check_modes(cfg)
    check_mode_refs(cfg, all_modes)
    check_regex_dup(cfg)
    check_hit_rate(cfg)
    check_translation(cfg)

    if INFO:
        print('\n【信息】')
        for m in INFO:
            print('  ·', m)
    if WARNS:
        print('\n【警告】%d 项' % len(WARNS))
        for m in WARNS:
            print('  !', m)
    if ERRORS:
        print('\n【错误】%d 项' % len(ERRORS))
        for m in ERRORS:
            print('  x', m)
    else:
        print('\n【错误】0 项')

    ok = not ERRORS and (not args.strict or not WARNS)
    print('\n结论：%s' % ('通过' if ok else '未通过'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
