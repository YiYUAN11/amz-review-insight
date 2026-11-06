/* ==========================================================================
   二级标签细分视图（c2）
   左侧：一级大类 → 二级标签树；右侧：细分模式 + 精选原文 + 全部原文墙
   ========================================================================== */
(function () {
  'use strict';

  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, m =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
  const fmt = n => (n == null ? '—' : Number(n).toLocaleString('en-US'));
  const pct = n => (n == null ? '—' : Number(n).toFixed(2) + '%');

  const C1_COLOR = {
    'Listing预期不符': '#e05c4b',
    '结构/功能配件': '#e08a2b',
    '产品做工&材质': '#d9a41f',
    '尺寸贴合': '#c9b52f',
    '包装物流': '#4fa356',
    '外观手感': '#2f9494',
    '使用体验': '#2563eb',
    '性价比': '#7c3aed',
    '其他': '#8794a6'
  };
  const c1c = n => C1_COLOR[n] || '#8794a6';

  let D = null;
  let TREE = null;
  let cur = null;          // 当前二级标签对象
  let subMode = 'mode';    // mode | cat3 | dim
  let wallData = [];       // 当前细分组的全部原文

  function init() {
    if (!window.__INSIGHT_DATA__ || !window.__INSIGHT_DATA__.cat2_tree) return;
    D = window.__INSIGHT_DATA__;
    TREE = D.cat2_tree;

    // KPI 补充
    const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    set('kpi-c2', fmt(D.kpi.cat2_count));
    set('kpi-c2sub', fmt(D.kpi.cat2_sub_count));

    renderSide();
    // 默认选中：条数最多且有多个细分的二级标签（跳过平台理由这类无信息的）
    const cand = TREE.filter(t =>
      t.n > 0 && !/平台理由|未细分/.test(t.cat2) &&
      (t.subcats || []).length > 1);
    cur = cand.sort((a, b) => b.n - a.n)[0] ||
          TREE.slice().sort((a, b) => b.n - a.n)[0] || TREE[0];
    selectCat2(cur);

    // 视图切换
    $$('#view-tabs button').forEach(b => {
      b.addEventListener('click', () => {
        $$('#view-tabs button').forEach(x => x.classList.remove('on'));
        b.classList.add('on');
        const v = b.dataset.view;
        $$('.view-pane').forEach(p => p.classList.toggle('on', p.id === 'view-' + v));
      });
    });

    // 细分口径切换
    $$('#sub-mode-tabs button').forEach(b => {
      b.addEventListener('click', () => {
        $$('#sub-mode-tabs button').forEach(x => x.classList.remove('on'));
        b.classList.add('on');
        subMode = b.dataset.mode;
        renderSubcats();
      });
    });

    // 原文墙筛选
    const inp = $('#c2-wall-search');
    if (inp) inp.addEventListener('input', renderWall);
    const sel = $('#c2-wall-src');
    if (sel) sel.addEventListener('change', renderWall);
  }

  /* ---------- 左侧标签树 ---------- */
  function renderSide() {
    const box = $('#c2-side');
    if (!box) return;
    // 按一级大类分组
    const byC1 = {};
    TREE.forEach(t => {
      (byC1[t.cat1] = byC1[t.cat1] || []).push(t);
    });
    const order = ['Listing预期不符', '结构/功能配件', '产品做工&材质', '尺寸贴合',
                   '包装物流', '外观手感', '使用体验', '性价比', '其他'];

    let html = '<div class="c2-side-title">一级大类 / 二级标签（点击切换）</div>';
    order.forEach(c1 => {
      const list = byC1[c1];
      if (!list) return;
      const tot = list.reduce((s, t) => s + t.n, 0);
      html += '<div class="c2-grp">' +
        '<div class="c2-grp-head" data-c1="' + esc(c1) + '">' +
          '<i class="dot" style="background:' + c1c(c1) + '"></i>' +
          '<span>' + esc(c1) + '</span>' +
          '<span class="cnt">' + fmt(tot) + '</span>' +
          '<span class="arw">▾</span>' +
        '</div><div class="c2-grp-items">';
      list.forEach(t => {
        html += '<button class="c2-item" data-key="' + esc(t.cat1 + '||' + t.cat2) + '">' +
          '<span class="nm">' + esc(t.cat2) + '</span>' +
          '<span class="nn">' + fmt(t.n) + '</span>' +
        '</button>';
      });
      html += '</div></div>';
    });
    box.innerHTML = html;

    // 折叠
    $$('#c2-side .c2-grp-head').forEach(h => {
      h.addEventListener('click', () => {
        const it = h.nextElementSibling;
        const on = it.style.display !== 'none';
        it.style.display = on ? 'none' : 'block';
        h.querySelector('.arw').textContent = on ? '▸' : '▾';
      });
    });
    // 选择
    $$('#c2-side .c2-item').forEach(b => {
      b.addEventListener('click', () => {
        const [c1, c2] = b.dataset.key.split('||');
        selectCat2(TREE.find(t => t.cat1 === c1 && t.cat2 === c2));
      });
    });
  }

  function selectCat2(t) {
    if (!t) return;
    cur = t;
    $$('#c2-side .c2-item').forEach(b => {
      b.classList.toggle('on', b.dataset.key === (t.cat1 + '||' + t.cat2));
    });
    renderHead();
    renderSubcats();
    // 原文墙默认展示该二级标签的全部原文
    wallData = t.all_quotes || [];
    const wh = $('#c2-wall-title');
    if (wh) wh.textContent = t.cat2 + ' · 全部原文';
    renderWall();
    const main = $('#c2-main');
    if (main && window.innerWidth < 1000) main.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* ---------- 右侧头部 ---------- */
  function renderHead() {
    const box = $('#c2-head');
    if (!box) return;
    box.style.borderLeftColor = c1c(cur.cat1);
    box.innerHTML =
      '<div class="crumb">' + esc(cur.cat1) + ' &nbsp;›&nbsp; 二级标签</div>' +
      '<h3>' + esc(cur.cat2) + '</h3>' +
      '<div class="stats">' +
        '<span>负面观点 <b>' + fmt(cur.n) + '</b> 条</span>' +
        '<span>占全部负面 <b>' + pct(cur.pct_of_neg) + '</b></span>' +
        '<span>退货来源 <b>' + fmt(cur.ret) + '</b> 条</span>' +
        '<span>评论来源 <b>' + fmt(cur.rev) + '</b> 条</span>' +
        '<span>可拆出 <b>' + getSubcats(cur).length + '</b> 种细分</span>' +
      '</div>';
  }

  /* ---------- 细分口径 ---------- */
  // 引擎输出 subcats 为扁平数组（每项含 key/desc/n/pct/ret/rev/quotes/all_quotes）。
  // 这里按 key 的语义自动归入三种口径，供用户切换。
  const MODE_HINTS = ['断裂', '脱落', '撑不住', '自转', '卡涩', '形变', '结构强度', '异响',
    '磁吸', '对位', '干扰', '顶膜', '气泡', '粘着', '尺寸不匹配', '有损', '配件缺失',
    '贴膜体验', '脱落', '扣合', '开合', '使用受阻', '变形', '单薄', '偏软', '厚重',
    '廉价', '脆弱', '粗糙', '防护不足', '开孔', '无防护', '覆盖不足', '宣传误导',
    '不工作', '不兼容', '短期失效', '未细分', '断裂脱落', '松动自转'];
  const CAT3_HINTS = ['未细分', '未指明', '其他', '泛称'];
  const DIM_HINTS = ['材质/做工', '铰链/中轴', '屏幕保护膜', '中框/边框', '支架/指环',
    '磁吸/充电', '前屏盖', '尺寸/适配', '外观手感', '使用体验', '包装物流', '其他'];

  function classifySub(s) {
    const k = (s.key || '');
    const d = (s.desc || '');
    if (CAT3_HINTS.some(h => k.includes(h) || d.includes(h))) return 'cat3';
    if (DIM_HINTS.some(h => k.includes(h) || d.includes(h))) return 'dim';
    if (MODE_HINTS.some(h => k.includes(h) || d.includes(h))) return 'mode';
    return 'mode';
  }

  function getSubcats(t) {
    const raw = t.subcats || [];
    if (!Array.isArray(raw)) {
      // 兼容字典结构 {mode:[], cat3:[], dim:[]}
      return raw.mode || [];
    }
    const buckets = { mode: [], cat3: [], dim: [] };
    raw.forEach(s => buckets[classifySub(s)].push(s));
    // 只有一个口径时，三个 tab 都用它
    const nonEmpty = ['mode', 'cat3', 'dim'].filter(k => buckets[k].length);
    if (nonEmpty.length === 1) {
      const only = nonEmpty[0];
      buckets.mode = buckets.mode.length ? buckets.mode : raw;
      buckets.cat3 = buckets.cat3.length ? buckets.cat3 : buckets.mode;
      buckets.dim = buckets.dim.length ? buckets.dim : buckets.mode;
    }
    return buckets[subMode] || [];
  }
  function renderSubcats() {
    const box = $('#c2-subs');
    if (!box) return;
    const list = getSubcats(cur);
    const modeLabel = { mode: '失效模式', cat3: '三级细分标签', dim: '部件维度' }[subMode];
    $('#c2-sub-hint').textContent = '当前口径：' + modeLabel + '（共 ' + list.length + ' 组，分母＝该二级标签内部 ' + fmt(cur.n) + ' 条）';

    const maxN = Math.max.apply(null, list.map(x => x.n).concat([1]));
    box.innerHTML = list.map((s, i) => {
      const qs = s.quotes || [];
      // mode 口径自带全部原文；cat3/dim 口径从该二级标签的全部原文里按口径值过滤
      let all = s.all_quotes || [];
      if (!all.length) {
        const field = subMode === 'cat3' ? 'cat3' : (subMode === 'dim' ? 'dim' : 'mode');
        all = (cur.all_quotes || []).filter(x => (x[field] || '') === (s.key || ''));
        if (!all.length) all = qs;
      }
      const quotesHtml = all.slice(0, 12).map(q => quoteHtml(q)).join('');
      const more = all.length > 12
        ? '<div style="font-size:11px;color:var(--text-mute);padding:4px 2px">… 另有 ' +
          (all.length - 12) + ' 条原文，见下方「全部原文墙」</div>' : '';
      return '<div class="c2-sub' + (i < 2 ? ' open' : '') + '" data-idx="' + i + '">' +
        '<div class="c2-sub-bar"><i style="width:' + (s.n / maxN * 100) + '%"></i></div>' +
        '<div class="c2-sub-head">' +
          '<div>' +
            '<div class="c2-sub-name">' + esc(s.key || '—') +
              '<span class="c2-sub-tag">' + esc(modeLabel) + '</span></div>' +
            (s.desc ? '<div class="c2-sub-desc">' + esc(s.desc) + '</div>' : '') +
          '</div>' +
          '<div class="c2-sub-n">' + fmt(s.n) + '</div>' +
          '<div class="c2-sub-pct">' + pct(s.pct) +
            '<small>占本标签</small></div>' +
        '</div>' +
        '<div class="c2-sub-body">' +
          '<div class="c2-sub-src">' +
            '<span>退货来源 <b>' + fmt(s.ret) + '</b></span>' +
            '<span>评论来源 <b>' + fmt(s.rev) + '</b></span>' +
            '<span>占全部负面 <b>' + pct(cur.pct_of_neg * s.pct / 100) + '</b></span>' +
            '<button class="c2-wall-btn" data-wall="' + i + '" ' +
              'style="margin-left:auto;font-family:inherit;font-size:11px;color:var(--accent);' +
              'background:#eaf1fe;border:1px solid #c7dbfb;border-radius:6px;padding:4px 10px;cursor:pointer">' +
              '查看本组全部原文（' + all.length + '）</button>' +
          '</div>' +
          '<div class="c2-quotes">' + quotesHtml + more + '</div>' +
        '</div>' +
      '</div>';
    }).join('');

    // 折叠
    $$('#c2-subs .c2-sub-head').forEach(h => {
      h.addEventListener('click', e => {
        if (e.target.closest('.c2-wall-btn')) return;
        h.parentElement.classList.toggle('open');
      });
    });
    // 「查看本组全部原文」
    $$('#c2-subs .c2-wall-btn').forEach(b => {
      b.addEventListener('click', e => {
        e.stopPropagation();
        const s = list[Number(b.dataset.wall)];
        // 与 renderSubcats 相同的口径过滤逻辑
        let wall = s.all_quotes || [];
        if (!wall.length) {
          const field = subMode === 'cat3' ? 'cat3' : (subMode === 'dim' ? 'dim' : 'mode');
          wall = (cur.all_quotes || []).filter(x => (x[field] || '') === (s.key || ''));
          if (!wall.length) wall = s.quotes || [];
        }
        wallData = wall;
        $('#c2-wall-title').textContent = cur.cat2 + ' › ' + (s.key || '') + ' · 全部原文';
        renderWall();
        $('#c2-wall-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }

  function quoteHtml(q) {
    const isRev = q.src === '买家评论';
    const zh = (q.zh || '').trim();
    const en = (q.t || '').trim();
    const tag = '<span class="qs ' + (isRev ? 'rev' : 'ret') + '">' +
      (isRev ? '评论' : '退货') + '</span>';
    if (zh && zh !== en) {
      return '<div class="c2-quote">' +
        '<div class="q-zh">' + esc(zh) + tag + '</div>' +
        '<div class="q-en">' + esc(en) + '</div>' +
      '</div>';
    }
    return '<div class="c2-quote">' + esc(en || zh) + tag + '</div>';
  }

  /* ---------- 全部原文墙 ---------- */
  function renderWall() {
    const box = $('#c2-wall');
    if (!box) return;
    const q = ($('#c2-wall-search')?.value || '').trim().toLowerCase();
    const src = $('#c2-wall-src')?.value || '';
    const filtered = (wallData || []).filter(x => {
      if (q && (x.t || '').toLowerCase().indexOf(q) < 0) return false;
      if (src === 'ret' && x.src === '买家评论') return false;
      if (src === 'rev' && x.src !== '买家评论') return false;
      return true;
    });
    $('#c2-wall-count').textContent = '显示 ' + fmt(filtered.length) + ' / ' + fmt((wallData || []).length) + ' 条';
    box.innerHTML = filtered.length
      ? filtered.map(quoteHtml).join('')
      : '<div class="c2-wall-empty">没有匹配的原文</div>';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 80));
  } else {
    setTimeout(init, 80);
  }
})();
