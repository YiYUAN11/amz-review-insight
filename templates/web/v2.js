/* ==========================================================================
   v2 渲染：维度 → 失效模式 → 原文证据
   替代原「三级下钻」章节，粒度更细、每条都带证据
   ========================================================================== */
(function () {
  'use strict';

  const $ = s => document.querySelector(s);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, m =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
  const fmt = n => (n == null ? '—' : Number(n).toLocaleString('en-US'));
  const pct = n => (n == null ? '—' : Number(n).toFixed(2) + '%');

  const DIM_COLOR = {
    '平台理由': '#8794a6',
    '材质/做工': '#d9a41f',
    '铰链/中轴': '#dc2626',
    '屏幕保护膜': '#e08a2b',
    '中框/边框': '#c9611f',
    '支架/指环': '#d95a7c',
    '尺寸/适配': '#c9b52f',
    '磁吸/充电': '#2563eb',
    '前屏盖': '#9333ea',
    '外观手感': '#0d9488',
    '使用体验': '#4fa356',
    '包装物流': '#7d9163',
    '正向体验': '#059669',
    '性价比': '#7c3aed',
    '其他': '#8794a6'
  };
  const dc = n => DIM_COLOR[n] || '#8794a6';

  let D = null;
  let curDim = null;
  let saveZone = null;

  /* ---------- 维度总览 ---------- */
  function renderDimGrid() {
    const box = $('#dim-grid');
    if (!box) return;
    box.innerHTML = '';
    const dims = D.dims.filter(d => d.dim !== '平台理由');
    const max = Math.max(...dims.map(d => d.n));

    // 平台理由单独一张卡片置前
    const plat = D.dims.find(d => d.dim === '平台理由');
    if (plat) {
      const t = document.createElement('div');
      t.className = 'dim-tile' + (curDim === '平台理由' ? ' active' : '');
      t.style.opacity = '.85';
      t.innerHTML =
        '<div class="dt-name"><span style="width:8px;height:8px;border-radius:2px;background:' +
        dc('平台理由') + ';display:inline-block"></span>平台理由（下拉项）</div>' +
        '<div class="dt-bar"><i style="width:' + (plat.n / max * 100) + '%;background:' +
        dc('平台理由') + '"></i></div>' +
        '<div class="dt-num"><b>' + fmt(plat.n) + '</b> 条 · 占负面 ' + pct(plat.pct) + '</div>' +
        '<div class="dt-modes">平台固定选项，非买家自由描述</div>';
      t.addEventListener('click', () => selectDim('平台理由'));
      box.appendChild(t);
    }

    dims.forEach(d => {
      const t = document.createElement('div');
      t.className = 'dim-tile' + (curDim === d.dim ? ' active' : '');
      t.innerHTML =
        '<div class="dt-name"><span style="width:8px;height:8px;border-radius:2px;background:' +
        dc(d.dim) + ';display:inline-block"></span>' + esc(d.dim) + '</div>' +
        '<div class="dt-bar"><i style="width:' + (d.n / max * 100) + '%;background:' +
        dc(d.dim) + '"></i></div>' +
        '<div class="dt-num"><b>' + fmt(d.n) + '</b> 条 · 占负面 ' + pct(d.pct) + '</div>' +
        '<div class="dt-modes">' + d.modes.length + ' 种具体表现</div>';
      t.addEventListener('click', () => selectDim(d.dim));
      box.appendChild(t);
    });
  }

  function selectDim(name) {
    curDim = name;
    renderDimGrid();
    renderModePanel();
    const p = $('#mode-panel');
    if (p) p.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* ---------- 模式面板 ---------- */
  function renderModePanel() {
    const box = $('#mode-panel');
    if (!box) return;
    const d = D.dims.find(x => x.dim === curDim);
    if (!d) { box.innerHTML = ''; return; }

    const head = document.createElement('div');
    head.style.cssText = 'display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:14px';
    head.innerHTML =
      '<span style="font-size:17px;font-weight:700">' + esc(d.dim) + '</span>' +
      '<span style="font-size:12.5px;color:var(--text-dim)">共 <b style="color:var(--text)">' +
      fmt(d.n) + '</b> 条 · 占全部负面 <b style="color:var(--text)">' + pct(d.pct) + '</b></span>' +
      '<span style="margin-left:auto;font-size:12px;color:var(--text-mute)">拆出 ' +
      d.modes.length + ' 种失效模式</span>';
    box.innerHTML = '';
    box.appendChild(head);

    const maxN = Math.max(...d.modes.map(m => m.n));
    d.modes.forEach((m, i) => {
      const blk = document.createElement('div');
      blk.className = 'mode-block' + (i < 2 ? ' open' : '');

      const quotesHtml = (m.quotes || []).map(q => {
        const zh = (q.zh || '').trim();
        const en = (q.t || '').trim();
        return '<div class="qline">' +
          (zh && zh !== en
            ? '<div style="font-weight:500">' + esc(zh) + '</div>' +
              '<div style="font-size:11px;color:var(--text-mute);font-style:italic;margin-top:2px">' + esc(en) + '</div>'
            : esc(en || zh)) +
          '<span class="qs' + (q.src === '买家评论' ? ' rev' : '') + '">' +
          (q.src === '买家评论' ? '评论' : '退货报告') + '</span></div>';
      }).join('');

      blk.innerHTML =
        '<div class="mode-head">' +
          '<div class="mh-l">' +
            '<div class="mh-mode">' + esc(m.mode) +
              '<span style="font-size:10.5px;font-weight:500;color:var(--text-mute);' +
              'border:1px solid var(--line);border-radius:4px;padding:0 5px">' +
              d.dim + '</span></div>' +
            '<div class="mh-phen">' + esc(m.phen || '') + '</div>' +
          '</div>' +
          '<div class="mh-num">' + fmt(m.n) + '</div>' +
          '<div class="mh-pct">' + pct(m.pct_in_dim) + '<small>占本维度</small></div>' +
        '</div>' +
        '<div class="mode-body">' +
          '<div class="src-split">' +
            '<span>退货来源 <b>' + fmt(m.ret) + '</b> 条</span>' +
            '<span>评论来源 <b>' + fmt(m.rev) + '</b> 条</span>' +
            '<span>占全部负面 <b>' + pct(m.pct_of_neg) + '</b></span>' +
          '</div>' +
          '<div class="qbox">' + quotesHtml + '</div>' +
        '</div>';

      blk.querySelector('.mode-head').addEventListener('click', () => blk.classList.toggle('open'));
      box.appendChild(blk);
    });
  }

  /* ---------- 全部原文证据墙 ---------- */
  function renderEvidenceWall() {
    const box = $('#qwall');
    if (!box) return;
    // 取当前维度的所有明细原文
    const items = D.detail.filter(o =>
      o.sent === '负面' && o.dim === curDim && o.snip && o.snip.length > 8);
    // 去重
    const seen = new Set();
    const uniq = [];
    items.forEach(o => {
      const k = o.snip.toLowerCase().replace(/[^a-z ]/g, '').slice(0, 40);
      if (seen.has(k)) return;
      seen.add(k);
      uniq.push(o);
    });
    box.innerHTML = uniq.slice(0, 300).map(o => {
      const zh = (o.snip_zh || o.zh || '').trim();
      const en = (o.snip || o.t || '').trim();
      return '<div class="qline">' +
        (zh && zh !== en
          ? '<div style="font-weight:500">' + esc(zh) + '</div>' +
            '<div style="font-size:11px;color:var(--text-mute);font-style:italic;margin-top:2px">' + esc(en) + '</div>'
          : esc(en || zh)) +
        '<span class="qs' + (o.src === '买家评论' ? ' rev' : '') + '" style="margin-left:6px">' +
        esc(o.mode) + '</span></div>';
    }).join('');
    const cnt = $('#qwall-count');
    if (cnt) cnt.textContent = '共 ' + fmt(items.length) + ' 条，去重后 ' + fmt(uniq.length) + ' 条';
  }

  /* ---------- 来源差异条 ---------- */
  function renderSrcBar() {
    const box = $('#src-bars');
    if (!box) return;
    const list = D.src_cmp.slice(0, 12);
    const max = Math.max(...list.map(x => Math.max(x.ret, x.rev)));
    box.innerHTML = list.map(x => {
      const up = x.diff > 0;
      return '<div class="stat-row">' +
        '<div class="sr-name">' + esc(x.name) + '</div>' +
        '<div class="sr-track" style="position:relative">' +
          '<div class="sr-fill" style="position:absolute;top:0;height:4px;width:' +
          (x.ret / max * 100) + '%;background:var(--neg)"></div>' +
          '<div class="sr-fill" style="position:absolute;bottom:0;height:4px;width:' +
          (x.rev / max * 100) + '%;background:var(--accent)"></div>' +
        '</div>' +
        '<div class="sr-val" style="color:' + (up ? 'var(--neg)' : 'var(--accent)') + '">' +
        (up ? '+' : '') + x.diff.toFixed(2) + '</div>' +
      '</div>';
    }).join('');
  }

  /* ---------- 初始化 ---------- */
  function boot() {
    if (!window.__INSIGHT_DATA__) return;
    D = window.__INSIGHT_DATA__;
    if (!D.dims) { console.warn('旧版数据，跳过 v2 渲染'); return; }

    // 修正 KPI 里维度数（s2 的 l3-summary 与 s3 的部件维度视图各有一组 id）
    const k = D.kpi;
    const setTxt = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    setTxt('kpi-dim', fmt(k.dim_count));
    setTxt('kpi-mode', fmt(k.mode_count));
    setTxt('kpi-plat', fmt(k.platform_cnt));
    setTxt('kpi-dim-c2', fmt(k.dim_count));
    setTxt('kpi-plat-c2', fmt(k.platform_cnt));

    curDim = D.dims.find(d => d.dim !== '平台理由').dim;
    renderDimGrid();
    renderModePanel();
    renderEvidenceWall();
    renderSrcBar();
  }

  window.__selectDim = selectDim;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 60));
  } else {
    setTimeout(boot, 60);
  }
})();
