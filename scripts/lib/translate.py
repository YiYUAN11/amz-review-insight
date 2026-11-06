# -*- coding: utf-8 -*-
"""翻译器：短语优先 + 逐词兜底，预编译保证性能"""
import re

from dict_zh import PHRASES, WORDS

# 品牌名保留不译
KEEP_EN = {'magsafe', 'iphone', 'duo', 'anker', 'spigen', 'idk', 'na', 'usb', 'type-c'}


def _norm(s):
    s = s.replace("'", '').replace('\u2019', '')
    s = re.sub(r'[^a-z0-9 ]', ' ', s.lower())
    return re.sub(r'\s+', ' ', s).strip()


EXACT = {}
for en, zh in PHRASES:
    EXACT[_norm(en)] = zh

PAT_PHRASE = re.compile(
    '|'.join('(?P<p%d>(?<![a-z])%s(?![a-z]))' % (
        i, re.escape(en.replace("'", '').replace('\u2019', '')))
        for i, (en, _) in enumerate(PHRASES)), re.I)
PHRASE_ZH = [zh for _, zh in PHRASES]

WORD_MAP = {en.lower(): zh for en, zh in WORDS}
PAT_WORD = re.compile(r"[a-z']+", re.I)


class Translator:
    def __init__(self, extra=None):
        self.extra = {k.lower(): v for k, v in (extra or {}).items()}
        self.cache = {}

    def __call__(self, text):
        if not text:
            return ''
        if text in self.cache:
            return self.cache[text]
        r = self._translate(text)
        self.cache[text] = r
        return r

    def _translate(self, s):
        low = s.replace("'", '').replace('\u2019', '').strip()

        # 整句命中
        n = _norm(low)
        if n in EXACT:
            return EXACT[n]

        # 扫描短语
        out, pos = [], 0
        for m in PAT_PHRASE.finditer(low):
            if m.start() > pos:
                seg = low[pos:m.start()]
                out.append(self._words(seg))
            out.append(PHRASE_ZH[int(m.lastgroup[1:])])
            pos = m.end()
        if pos < len(low):
            out.append(self._words(low[pos:]))
        res = ''.join(out)

        # 清理
        res = re.sub(r'\s+', ' ', res).strip()
        res = re.sub(r'\s+([,.!;:?])', r'\1', res)
        res = re.sub(r'([,.!;:?])\s+', r'\1', res)
        res = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', res)
        res = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[，。、；：！？])', '', res)
        res = res.strip(' ,.;:')
        if not re.search(r'[\u4e00-\u9fff]', res):
            return ''
        return res

    def _words(self, seg):
        def sub(m):
            w = m.group(0)
            lw = w.lower()
            if lw in self.extra:
                return self.extra[lw]
            if lw in KEEP_EN:
                return w
            return WORD_MAP.get(lw, w)
        return PAT_WORD.sub(sub, seg)
