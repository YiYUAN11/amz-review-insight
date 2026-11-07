/* ==========================================================================
   亚马逊退货 & 评论洞察 · 可视化逻辑
   纯原生实现：SVG 图表 + 表格渲染 + 交互筛选
   ========================================================================== */
(function () {
  'use strict';

  /* ---------------- 配色 ---------------- */
  const C = {
    neg: '#dc2626', negDeep: '#b91c1c', pos: '#059669', neu: '#64748b',
    accent: '#2563eb', warn: '#d97706', purple: '#7c3aed', teal: '#0d9488'
  };

  // 一级大类配色（9 类，语义化：问题类偏红/橙，中性偏灰）
  const CAT1_COLOR = {
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
  const cat1Color = n => CAT1_COLOR[n] || '#8794a6';

  /* ---------------- 工具 ---------------- */
  const $ = s => document.querySelector(s);
  const el = (tag, cls, txt) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined) e.textContent = txt;
    return e;
  };
  const UNSPEC = '未指明（原文无具体落点）';
  const fmt = n => (n == null ? '—' : n.toLocaleString('en-US'));
  const pct = n => (n == null || !isFinite(n) ? '—' : n.toFixed(2) + '%');
  const esc = s => String(s).replace(/[&<>"']/g, m =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));

  /* ---------------- 提示框 ---------------- */
  const tip = $('#tooltip');
  function showTip(evt, html) {
    tip.innerHTML = html;
    tip.classList.add('on');
    moveTip(evt);
  }
  function moveTip(evt) {
    const pad = 14;
    let x = evt.clientX + pad, y = evt.clientY + pad;
    const r = tip.getBoundingClientRect();
    if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - pad;
    if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - pad;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
  const hideTip = () => tip.classList.remove('on');

  function bindTip(node, htmlFn) {
    node.addEventListener('mouseenter', e => showTip(e, htmlFn()));
    node.addEventListener('mousemove', moveTip);
    node.addEventListener('mouseleave', hideTip);
  }

  /* ---------------- SVG 基础 ---------------- */
  const NS = 'http://www.w3.org/2000/svg';
  function svgEl(tag, attrs) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) {
      if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    }
    return n;
  }
  function makeSvg(w, h) {
    const s = svgEl('svg', { viewBox: `0 0 ${w} ${h}`, width: '100%', height: h });
    s.style.maxWidth = w + 'px';
    s.style.margin = '0 auto';
    return s;
  }

  /* 环形/饼图扇区路径 */
  function arcPath(cx, cy, rOut, rIn, a0, a1) {
    const p = (r, a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    const lg = (a1 - a0) > Math.PI ? 1 : 0;
    const [x0, y0] = p(rOut, a0), [x1, y1] = p(rOut, a1);
    const [x2, y2] = p(rIn, a1), [x3, y3] = p(rIn, a0);
    if (rIn === 0) {
      return `M ${cx} ${cy} L ${x0} ${y0} A ${rOut} ${rOut} 0 ${lg} 1 ${x1} ${y1} Z`;
    }
    return `M ${x0} ${y0} A ${rOut} ${rOut} 0 ${lg} 1 ${x1} ${y1} ` +
           `L ${x2} ${y2} A ${rIn} ${rIn} 0 ${lg} 0 ${x3} ${y3} Z`;
  }

  /* ==========================================================================
     数据
     ========================================================================== */
  let D = null;

  /* ==========================================================================
     KPI
     ========================================================================== */
  function renderKpi() {
    const k = D.kpi;
    const items = [
      { label: '原始文本', value: fmt(k.raw_total), foot: `退货 ${fmt(k.raw_ret)} + 评论 ${fmt(k.raw_rev)}`, cls: '' },
      { label: '拆分后独立观点', value: fmt(k.total), foot: `平均 ${k.avg_per_text} 条 / 原文`, cls: '' },
      { label: '负面观点', value: fmt(k.negN), foot: `占全部观点 ${pct(k.neg_pct)}`, cls: 'neg' },
      { label: '中性观点', value: fmt(k.neu), foot: `占全部观点 ${pct(k.neu_pct)}`, cls: 'neu' },
      { label: '正向观点', value: fmt(k.pos), foot: `占全部观点 ${pct(k.pos_pct)}`, cls: 'pos' },
      { label: '有明确具象点', value: fmt(k.spec), foot: `占全部观点 ${pct(k.spec_pct)}`, cls: 'warn' },
      { label: '归类存疑', value: fmt(k.doubt), foot: `占全部观点 ${pct(k.doubt_pct)}`, cls: 'warn' }
    ];
    const box = $('#kpi-grid');
    items.forEach(it => {
      const d = el('div', 'kpi ' + it.cls);
      d.appendChild(el('div', 'label', it.label));
      const v = el('div', 'value');
      v.textContent = it.value;
      d.appendChild(v);
      d.appendChild(el('div', 'foot', it.foot));
      box.appendChild(d);
    });

    $('#m-raw').textContent = fmt(k.raw_total);
    $('#m-total').textContent = fmt(k.total);
    $('#s2-total').textContent = fmt(k.total);
    $('#s2-denom-tag').textContent = `分母：${fmt(k.total)} 条`;
    $('#s3-neg').textContent = fmt(k.negN);
    $('#s5-total').textContent = fmt(k.total);
    $('#doubt-n').textContent = fmt(k.doubt);
    $('#doubt-pct').textContent = pct(k.doubt_pct);
    $('#s4-ret').textContent = fmt(k.ret_op);
    $('#s4-rev').textContent = fmt(k.rev_op);
  }

  /* ==========================================================================
     饼图（情感 / 具象 / 来源 三个小环形 + 大类大饼）
     ========================================================================== */
  function donut(container, data, opts) {
    const o = Object.assign({
      size: 210, thick: 0.42, centerTop: null, centerBot: null,
      legend: null, colors: null, labelMin: 6
    }, opts || {});

    const box = $(container);
    box.innerHTML = '';
    const w = o.size, h = o.size, cx = w / 2, cy = h / 2;
    const rOut = Math.min(w, h) / 2 - 4;
    const rIn = rOut * (1 - o.thick);
    const total = data.reduce((s, d) => s + d.n, 0) || 1;

    const svg = makeSvg(w, h);
    let a = -Math.PI / 2;

    data.forEach(d => {
      const frac = d.n / total;
      const a1 = a + frac * Math.PI * 2;
      const color = (o.colors && o.colors[d.name]) || cat1Color(d.name);
      const path = svgEl('path', {
        d: arcPath(cx, cy, rOut, rIn, a, a1),
        fill: color,
        stroke: '#ffffff',
        'stroke-width': 1.6
      });
      path.style.cursor = 'pointer';
      path.style.transition = 'opacity .16s';
      bindTip(path, () =>
        `<div class="t-name">${esc(d.name)}</div>
         <div class="t-row">条数 <b>${fmt(d.n)}</b></div>
         <div class="t-row">占比 <b>${pct(d.n / total * 100)}</b></div>`);
      path.addEventListener('mouseenter', () => path.style.opacity = .82);
      path.addEventListener('mouseleave', () => path.style.opacity = 1);
      svg.appendChild(path);

      // 扇区标签（占比够大才显示）
      if (frac * 100 >= o.labelMin) {
        const mid = (a + a1) / 2, rMid = (rOut + rIn) / 2;
        const t = svgEl('text', {
          x: cx + rMid * Math.cos(mid),
          y: cy + rMid * Math.sin(mid),
          fill: '#ffffff', 'font-size': 11, 'font-weight': 700,
          'text-anchor': 'middle', 'dominant-baseline': 'middle',
          'pointer-events': 'none'
        });
        t.textContent = Math.round(frac * 100) + '%';
        svg.appendChild(t);
      }
      a = a1;
    });

    // 中心文字
    if (o.centerTop) {
      const t1 = svgEl('text', {
        x: cx, y: cy - 6, fill: '#1c2738', 'font-size': 19, 'font-weight': 700,
        'text-anchor': 'middle', 'dominant-baseline': 'middle'
      });
      t1.textContent = o.centerTop;
      svg.appendChild(t1);
    }
    if (o.centerBot) {
      const t2 = svgEl('text', {
        x: cx, y: cy + 15, fill: '#8b98a9', 'font-size': 10.5,
        'text-anchor': 'middle', 'dominant-baseline': 'middle'
      });
      t2.textContent = o.centerBot;
      svg.appendChild(t2);
    }

    box.appendChild(svg);
  }

  function renderSentiment() {
    const k = D.kpi;
    const data = [
      { name: '负面', n: k.negN },
      { name: '中性', n: k.neu },
      { name: '正向', n: k.pos }
    ];
    const colors = { '负面': C.neg, '中性': C.neu, '正向': C.pos };
    donut('#chart-sentiment', data, {
      size: 220, thick: .40, centerTop: fmt(k.total), centerBot: '全部观点',
      colors, labelMin: 3
    });
    legend('#legend-sentiment', data, colors, k.total);
  }

  function renderSpecific() {
    const k = D.kpi;
    const data = [
      { name: '有具象点', n: k.spec },
      { name: '无具象点', n: k.vague }
    ];
    const colors = { '有具象点': C.accent, '无具象点': '#c3cedd' };
    donut('#chart-specific', data, {
      size: 160, thick: .38, centerTop: pct(k.spec_pct), centerBot: '有具象点',
      colors, labelMin: 12
    });

    const data2 = [
      { name: '退货报告', n: k.ret_op || 0 },
      { name: '买家评论', n: k.rev_op || 0 }
    ];
    const colors2 = { '退货报告': C.negDeep, '买家评论': C.teal };
    donut('#chart-source', data2, {
      size: 160, thick: .38, centerTop: pct(k.rev_pct), centerBot: '评论占比',
      colors: colors2, labelMin: 20
    });

    // 退货来源具象率（该来源没有数据时显示「—」，不显示 NaN）
    const retSpec = D.detail.filter(d => d.src === '买家之声退货报告');
    const revSpec = D.detail.filter(d => d.src !== '买家之声退货报告');
    const rp = retSpec.length
      ? retSpec.filter(d => d.spec).length / retSpec.length * 100
      : null;
    const vp = revSpec.length
      ? revSpec.filter(d => d.spec).length / revSpec.length * 100
      : null;
    $('#ret-spec-rate').textContent = pct(rp);
    const revEl = document.getElementById('rev-spec-rate');
    if (revEl) revEl.textContent = pct(vp);
    // 退货来源没有样本时，换一句说明，不说「退货反馈中大量是平台下拉理由」
    const noteEl = document.getElementById('spec-rate-note-text');
    if (noteEl) {
      noteEl.textContent = retSpec.length
        ? '退货反馈中大量是平台下拉理由，缺乏落点——这是后续归因必须谨慎的原因。'
        : '本次数据仅包含评论来源（无退货报告样本），退货侧具象率暂不可得。';
    }
  }

  function legend(sel, data, colors, total) {
    const box = $(sel);
    if (!box) return;
    box.innerHTML = '';
    data.forEach(d => {
      const it = el('span', 'item');
      const dot = el('span', 'dot');
      dot.style.background = colors[d.name] || cat1Color(d.name);
      it.appendChild(dot);
      it.appendChild(document.createTextNode(
        `${d.name} ${fmt(d.n)}（${pct(d.n / total * 100)}）`));
      box.appendChild(it);
    });
  }

  /* ---------------- 大类大饼 ---------------- */
  function renderPie() {
    const data = D.cat1_all;
    const total = D.kpi.total;
    const box = $('#chart-pie');
    box.innerHTML = '';

    const w = 400, h = 400, cx = 200, cy = 200, rOut = 158, rIn = 0;
    const svg = makeSvg(w, h);
    let a = -Math.PI / 2;

    data.forEach(d => {
      const frac = d.n / total;
      const a1 = a + frac * Math.PI * 2;
      const color = cat1Color(d.name);
      const path = svgEl('path', {
        d: arcPath(cx, cy, rOut, rIn, a, a1),
        fill: color, stroke: '#ffffff', 'stroke-width': 2
      });
      path.style.cursor = 'pointer';
      path.style.transition = 'transform .18s, opacity .16s';
      path.style.transformOrigin = `${cx}px ${cy}px`;

      bindTip(path, () =>
        `<div class="t-name">${esc(d.name)}</div>
         <div class="t-row">观点条数 <b>${fmt(d.n)}</b></div>
         <div class="t-row">占全部观点 <b>${pct(d.n / total * 100)}</b></div>
         <div class="t-row" style="margin-top:4px;padding-top:4px;border-top:1px solid #e2e8f0">
           负面 ${fmt(d.neg)} · 中性 ${fmt(d.neu)} · 正向 ${fmt(d.pos)}</div>`);

      path.addEventListener('mouseenter', () => {
        path.style.transform = 'scale(1.035)';
        path.style.opacity = .88;
      });
      path.addEventListener('mouseleave', () => {
        path.style.transform = 'scale(1)';
        path.style.opacity = 1;
      });
      svg.appendChild(path);

      // 扇区外标签（占比 >= 4% 才标注，避免重叠）
      const p = frac * 100;
      if (p >= 4) {
        const mid = (a + a1) / 2;
        const rl = rOut * 1.11;
        const x = cx + rl * Math.cos(mid), y = cy + rl * Math.sin(mid);
        const anchor = Math.cos(mid) > 0.1 ? 'start' : (Math.cos(mid) < -0.1 ? 'end' : 'middle');
        const t = svgEl('text', {
          x, y: y - 5, fill: '#46566e', 'font-size': 11, 'font-weight': 600,
          'text-anchor': anchor, 'pointer-events': 'none'
        });
        t.textContent = d.name;
        svg.appendChild(t);
        const t2 = svgEl('text', {
          x, y: y + 9, fill: '#8b98a9', 'font-size': 10.5,
          'text-anchor': anchor, 'pointer-events': 'none'
        });
        t2.textContent = pct(p);
        svg.appendChild(t2);
      }
      a = a1;
    });

    box.appendChild(svg);

    const lg = $('#legend-pie');
    lg.innerHTML = '';
    data.forEach(d => {
      const it = el('span', 'item');
      const dot = el('span', 'dot');
      dot.style.background = cat1Color(d.name);
      it.appendChild(dot);
      it.appendChild(document.createTextNode(`${d.name} ${fmt(d.n)}（${pct(d.n / total * 100)}）`));
      lg.appendChild(it);
    });
  }

  /* ---------------- 表1 ---------------- */
  function renderTableCat1() {
    const tb = $('#table-cat1 tbody');
    const total = D.kpi.total;
    const max = Math.max(...D.cat1_all.map(d => d.n));
    D.cat1_all.forEach(d => {
      const tr = el('tr');
      tr.innerHTML = `
        <td>${esc(d.name)}</td>
        <td class="r">${fmt(d.n)}</td>
        <td class="r">${pct(d.n / total * 100)}</td>
        <td class="bar-cell">
          <div class="bar-bg"><div class="bar-fill" style="width:${d.n / max * 100}%;background:${cat1Color(d.name)}"></div></div>
        </td>`;
      tb.appendChild(tr);
    });
  }

  /* ---------------- 表2（可折叠分组）---------------- */
  function renderTableCat2() {
    const box = $('#table-cat2');
    box.innerHTML = '';
    D.neg_tree.forEach((g, gi) => {
      const grp = el('div');
      grp.style.cssText = 'margin-bottom:10px;border:1px solid var(--line-soft);border-radius:10px;overflow:hidden';

      const head = el('div');
      head.style.cssText = `display:flex;align-items:center;gap:10px;padding:11px 14px;cursor:pointer;
        background:var(--th-bg);border-left:3px solid ${cat1Color(g.name)};user-select:none`;
      head.innerHTML = `
        <span style="font-size:13px;font-weight:650">${esc(g.name)}</span>
        <span style="font-size:11.5px;color:var(--text-mute)">
          ${fmt(g.n)} 条 · 占全部负面 ${pct(g.pct)}</span>
        <span style="margin-left:auto;font-size:11px;color:var(--text-mute)" class="chev">▾</span>`;

      const body = el('div');
      body.style.cssText = 'display:none;padding:0 14px 10px';

      const maxIn = Math.max(...g.children.map(c => c.pct_in_cat1));
      const tbl = el('table');
      tbl.innerHTML = `<thead><tr>
          <th>二级标签</th><th class="r" style="width:70px">条数</th>
          <th class="r" style="width:96px">占大类内部</th>
          <th style="width:130px">分布</th></tr></thead>`;
      const tbody = el('tbody');
      g.children.forEach(c => {
        const tr = el('tr');
        tr.innerHTML = `
          <td>${esc(c.name)}</td>
          <td class="r">${fmt(c.n)}</td>
          <td class="r">${pct(c.pct_in_cat1)}</td>
          <td class="bar-cell"><div class="bar-bg">
            <div class="bar-fill" style="width:${c.pct_in_cat1 / maxIn * 100}%;background:${cat1Color(g.name)}"></div>
          </div></td>`;
        tbody.appendChild(tr);
      });
      tbl.appendChild(tbody);
      body.appendChild(tbl);

      head.addEventListener('click', () => {
        const open = body.style.display !== 'none';
        body.style.display = open ? 'none' : 'block';
        head.querySelector('.chev').textContent = open ? '▾' : '▴';
      });

      // 默认展开前两个
      if (gi < 2) {
        body.style.display = 'block';
        head.querySelector('.chev').textContent = '▴';
      }

      grp.appendChild(head);
      grp.appendChild(body);
      box.appendChild(grp);
    });
  }

  /* ==========================================================================
     嵌套环形图（一级 → 二级）
     ========================================================================== */
  function renderSunburst() {
    const tree = D.neg_tree;
    const total = D.kpi.negN;
    const box = $('#chart-sunburst');
    box.innerHTML = '';

    const w = 430, h = 430, cx = 215, cy = 215;
    const r1o = 132, r1i = 78;   // 内环（一级）
    const r2o = 196, r2i = 138;  // 外环（二级）
    const svg = makeSvg(w, h);

    let a = -Math.PI / 2;

    tree.forEach(g => {
      const gFrac = g.n / total;
      const gA1 = a + gFrac * Math.PI * 2;
      const baseColor = cat1Color(g.name);

      // --- 内环 ---
      const inner = svgEl('path', {
        d: arcPath(cx, cy, r1o, r1i, a, gA1),
        fill: baseColor, stroke: '#ffffff', 'stroke-width': 2
      });
      inner.style.cursor = 'pointer';
      inner.style.transition = 'opacity .16s';
      bindTip(inner, () =>
        `<div class="t-name">${esc(g.name)}</div>
         <div class="t-row">负面条数 <b>${fmt(g.n)}</b></div>
         <div class="t-row">占全部负面 <b>${pct(g.pct)}</b></div>
         <div class="t-row" style="margin-top:4px;padding-top:4px;border-top:1px solid #e2e8f0">
           含 ${g.children.length} 个二级痛点</div>`);
      svg.appendChild(inner);

      // 内环标签
      if (gFrac * 100 >= 4) {
        const mid = (a + gA1) / 2, rm = (r1o + r1i) / 2;
        const t = svgEl('text', {
          x: cx + rm * Math.cos(mid), y: cy + rm * Math.sin(mid),
          fill: '#ffffff', 'font-size': 10.5, 'font-weight': 700,
          'text-anchor': 'middle', 'dominant-baseline': 'middle', 'pointer-events': 'none'
        });
        t.textContent = Math.round(gFrac * 100) + '%';
        svg.appendChild(t);
      }

      // --- 外环：该大类下的二级 ---
      let b = a;
      const shades = g.children.length;
      g.children.forEach((c, i) => {
        const cFrac = c.n / total;
        const bA1 = b + cFrac * Math.PI * 2;
        // 同色系不同明度
        const light = 0.34 + (i / Math.max(1, shades - 1)) * 0.5;
        const col = mix(baseColor, '#ffffff', light * 0.62);

        const outer = svgEl('path', {
          d: arcPath(cx, cy, r2o, r2i, b, bA1),
          fill: col, stroke: '#ffffff', 'stroke-width': 1.4
        });
        outer.style.cursor = 'pointer';
        outer.style.transition = 'opacity .16s, transform .16s';
        outer.style.transformOrigin = `${cx}px ${cy}px`;
        bindTip(outer, () =>
          `<div class="t-name">${esc(c.name)}</div>
           <div class="t-row">所属大类 <b>${esc(g.name)}</b></div>
           <div class="t-row">条数 <b>${fmt(c.n)}</b></div>
           <div class="t-row">占该大类内部 <b>${pct(c.pct_in_cat1)}</b></div>
           <div class="t-row">占全部负面 <b>${pct(c.pct_of_neg)}</b></div>`);
        outer.addEventListener('mouseenter', () => {
          outer.style.opacity = .8;
          outer.style.transform = 'scale(1.012)';
          inner.style.opacity = 1;
        });
        outer.addEventListener('mouseleave', () => {
          outer.style.opacity = 1;
          outer.style.transform = 'scale(1)';
        });
        svg.appendChild(outer);
        b = bA1;
      });

      a = gA1;
    });

    // 中心
    const t1 = svgEl('text', {
      x: cx, y: cy - 8, fill: '#1c2738', 'font-size': 22, 'font-weight': 700,
      'text-anchor': 'middle', 'dominant-baseline': 'middle'
    });
    t1.textContent = fmt(total);
    svg.appendChild(t1);
    const t2 = svgEl('text', {
      x: cx, y: cy + 14, fill: '#8b98a9', 'font-size': 11,
      'text-anchor': 'middle', 'dominant-baseline': 'middle'
    });
    t2.textContent = '全部负面观点';
    svg.appendChild(t2);

    box.appendChild(svg);

    // 图例
    const lg = $('#legend-sunburst');
    lg.innerHTML = '';
    D.cat1_neg.forEach(d => {
      const it = el('span', 'item');
      const dot = el('span', 'dot');
      dot.style.background = cat1Color(d.name);
      it.appendChild(dot);
      it.appendChild(document.createTextNode(`${d.name} ${fmt(d.n)}（${pct(d.pct)}）`));
      lg.appendChild(it);
    });
  }

  /* 颜色混合 */
  function mix(hex1, hex2, t) {
    const h2r = h => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
    const a = h2r(hex1), b = h2r(hex2);
    const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
    return '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');
  }

  /* ---------------- 痛点 Top 列表 ---------------- */
  function renderPainList() {
    const box = $('#pain-list');
    box.innerHTML = '';
    D.neg_top.forEach((d, i) => {
      const item = el('div', 'pain-item' + (i < 3 ? ' top' : ''));
      const pname = d.name || d.mode || "—";
      const pmeta = d.dim ? (d.dim + (d.phen ? " · " + d.phen : "")) : (d.cat1 || "");
      item.innerHTML = `
        <div class="pain-rank">${i + 1}</div>
        <div>
          <div class="pain-name">${esc(pname)}</div>
          <div class="pain-meta">${esc(pmeta)}</div>
        </div>
        <div class="pain-val">${fmt(d.n)}<small>${pct(d.pct)} 占负面</small></div>`;
      box.appendChild(item);
    });
  }

  /* ==========================================================================
     三级痛点下钻
     ========================================================================== */
  const L3_COLORS = ['#dc2626', '#e08a2b', '#d9a41f', '#2563eb', '#0d9488',
                     '#7c3aed', '#db5b86', '#4fa356', '#8794a6'];

  function renderL3Summary() {
    const box = $('#l3-summary');
    if (!box) return;
    const tree = D.l3_tree || [];
    if (!tree.length) return;
    const totalL3 = tree.reduce((s, t) => s + t.n, 0);
    const biggest = tree.slice().sort((a, b) => b.n - a.n)[0];
    const finest = tree.slice().sort((a, b) => b.children.length - a.children.length)[0];
    const items = [
      ['已三级细分的痛点条目', fmt(totalL3)],
      ['涉及二级标签', tree.length + ' 类'],
      ['细分最细的一类', finest ? finest.l2 + '（' + finest.children.length + ' 种）' : '—'],
      ['体量最大的痛点', biggest ? biggest.l2 + '（' + fmt(biggest.n) + ' 条）' : '—']
    ];
    box.className = 'l3-summary';
    box.innerHTML = items.map(function (kv) {
      return '<div class="it"><span class="k">' + esc(kv[0]) +
             '</span><span class="v">' + esc(kv[1]) + '</span></div>';
    }).join('');
  }

  function renderDrill() {
    const box = $('#drill-grid');
    if (!box) return;
    box.innerHTML = '';
    const tree = D.l3_tree || [];
    if (!tree.length) return;

    tree.forEach(function (t, ti) {
      const card = el('div', 'drill-card' + (ti < 2 ? ' open' : ''));
      const color = cat1Color(t.l1);

      const head = el('div', 'drill-head');
      head.style.borderLeftColor = color;
      head.innerHTML =
        '<div class="hi">' +
          '<div class="l1">' + esc(t.l1) + '</div>' +
          '<div class="l2">' + esc(t.l2) + '</div>' +
          '<div class="stat">共 <b>' + fmt(t.n) + '</b> 条 · 占全部负面 <b>' + pct(t.pct_of_neg) +
          '</b> · 拆出 <b>' + t.children.length + '</b> 种具体表现</div>' +
        '</div><div class="chev">▾</div>';
      head.addEventListener('click', function () { card.classList.toggle('open'); });
      card.appendChild(head);

      const body = el('div', 'drill-body');
      const maxN = Math.max.apply(null, t.children.map(function (c) { return c.n; }));
      t.children.forEach(function (c, ci) {
        const row = el('div', 'l3-row');
        const cc = L3_COLORS[ci % L3_COLORS.length];
        const quotesHtml = (c.quotes || []).map(function (q) {
          return '<div class="quote">' + esc(q.text) +
            '<span class="src' + (q.src === '买家评论' ? ' rev' : '') + '">' +
            (q.src === '买家评论' ? '评论' : '退货') + '</span></div>';
        }).join('');

        row.innerHTML =
          '<div class="l3-top">' +
            '<span class="l3-name"><i class="l3-dot" style="background:' + cc + '"></i>' +
              esc(c.name) + '</span>' +
            '<span class="l3-num">' + fmt(c.n) + '</span>' +
            '<span class="l3-pct">占本类 ' + pct(c.pct_in_l2) +
              ' · 占全部负面 ' + pct(c.pct_of_neg) + '</span>' +
          '</div>' +
          '<div class="l3-bar"><i style="width:' + (c.n / maxN * 100) +
            '%;background:' + cc + '"></i></div>' +
          (c.desc ? '<div class="l3-desc">' + esc(c.desc) + '</div>' : '') +
          '<div class="quotes">' + quotesHtml + '</div>';
        body.appendChild(row);
      });
      card.appendChild(body);
      box.appendChild(card);
    });

    // 全部展开 / 收起
    const btn = document.getElementById('drill-all');
    if (btn && !btn.dataset.bound) {
      btn.dataset.bound = '1';
      btn.addEventListener('click', function () {
        const all = [...box.querySelectorAll('.drill-card')];
        const anyClosed = all.some(c => !c.classList.contains('open'));
        all.forEach(c => c.classList.toggle('open', anyClosed));
        btn.textContent = anyClosed ? '全部收起' : '全部展开';
      });
    }
  }

  /* ==========================================================================
     分组柱状图
     ========================================================================== */
  function renderGrouped() {
    const data = D.src_cmp;
    const box = $('#chart-grouped');
    box.innerHTML = '';

    const padL = 52, padR = 16, padT = 18, padB = 76;
    const w = 640, h = 330;
    const iw = w - padL - padR, ih = h - padT - padB;
    const svg = makeSvg(w, h);

    const maxV = Math.max(...data.map(d => Math.max(d.ret, d.rev)));
    const yMax = Math.ceil(maxV / 10) * 10;

    // 网格 + Y 轴
    for (let i = 0; i <= 4; i++) {
      const v = yMax / 4 * i;
      const y = padT + ih - (v / yMax) * ih;
      svg.appendChild(svgEl('line', {
        x1: padL, y1: y, x2: padL + iw, y2: y,
        stroke: '#e2e8f0', 'stroke-width': 1
      }));
      const t = svgEl('text', {
        x: padL - 9, y: y + 4, fill: '#8b98a9', 'font-size': 10.5, 'text-anchor': 'end'
      });
      t.textContent = Math.round(v) + '%';
      svg.appendChild(t);
    }

    const groupW = iw / data.length;
    const barW = Math.min(17, groupW * 0.3);
    const gap = 4;

    data.forEach((d, i) => {
      const gx = padL + groupW * i + groupW / 2;

      [{ v: d.ret, color: C.negDeep, label: '退货来源' },
       { v: d.rev, color: C.accent, label: '评论来源' }].forEach((s, si) => {
        const bh = (s.v / yMax) * ih;
        const x = gx - barW - gap / 2 + si * (barW + gap);
        const y = padT + ih - bh;

        const rect = svgEl('rect', {
          x, y, width: barW, height: Math.max(0, bh),
          fill: s.color, rx: 2.5
        });
        rect.style.cursor = 'pointer';
        rect.style.transition = 'opacity .14s';
        bindTip(rect, () =>
          `<div class="t-name">${esc(d.name)}</div>
           <div class="t-row">${s.label} <b>${pct(s.v)}</b></div>
           <div class="t-row">占该来源负面观点</div>`);
        rect.addEventListener('mouseenter', () => rect.style.opacity = .75);
        rect.addEventListener('mouseleave', () => rect.style.opacity = 1);
        svg.appendChild(rect);
      });

      // X 轴标签（旋转）
      const t = svgEl('text', {
        x: gx, y: padT + ih + 12,
        fill: '#5a687c', 'font-size': 10.5, 'text-anchor': 'end',
        transform: `rotate(-38 ${gx} ${padT + ih + 12})`
      });
      t.textContent = d.name.length > 9 ? d.name.slice(0, 8) + '…' : d.name;
      svg.appendChild(t);
    });

    // 轴线
    svg.appendChild(svgEl('line', {
      x1: padL, y1: padT + ih, x2: padL + iw, y2: padT + ih,
      stroke: '#cbd5e1', 'stroke-width': 1.2
    }));
    // Y 轴标题
    const yt = svgEl('text', {
      x: 13, y: padT + ih / 2, fill: '#8b98a9', 'font-size': 10.5,
      'text-anchor': 'middle', transform: `rotate(-90 13 ${padT + ih / 2})`
    });
    yt.textContent = '占该来源负面观点 %';
    svg.appendChild(yt);

    box.appendChild(svg);

    const lg = $('#legend-grouped');
    lg.innerHTML = '';
    [['退货来源', C.negDeep], ['评论来源', C.accent]].forEach(([n, c]) => {
      const it = el('span', 'item');
      const dot = el('span', 'dot');
      dot.style.background = c;
      it.appendChild(dot);
      it.appendChild(document.createTextNode(n));
      lg.appendChild(it);
    });
  }

  /* ---------------- 差异条 ---------------- */
  function renderDiff() {
    const box = $('#diff-list');
    box.innerHTML = '';
    const maxV = Math.max(...D.src_cmp.map(d => Math.max(d.ret, d.rev)));
    D.src_cmp.forEach(d => {
      const row = el('div', 'diff-row');
      const up = d.diff > 0;
      row.innerHTML = `
        <div class="diff-name">${esc(d.name)}</div>
        <div class="diff-track">
          <div class="diff-ret" style="width:${d.ret / maxV * 100}%"></div>
          <div class="diff-rev" style="width:${d.rev / maxV * 100}%"></div>
        </div>
        <div class="diff-val ${up ? 'up' : 'dn'}">${up ? '+' : ''}${d.diff.toFixed(2)}</div>`;
      // 悬停提示
      row.addEventListener('mouseenter', e => showTip(e,
        `<div class="t-name">${esc(d.name)}</div>
         <div class="t-row">退货来源 <b>${pct(d.ret)}</b></div>
         <div class="t-row">评论来源 <b>${pct(d.rev)}</b></div>
         <div class="t-row">差值 <b>${d.diff > 0 ? '+' : ''}${d.diff.toFixed(2)} pp</b></div>`));
      row.addEventListener('mousemove', moveTip);
      row.addEventListener('mouseleave', hideTip);
      box.appendChild(row);
    });
  }

  /* ==========================================================================
     明细表
     ========================================================================== */
  let filtered = [];

  function fillCat1Select() {
    const sel = $('#f-cat1');
    D.cat1_all.forEach(d => {
      const o = el('option', null, d.name);
      o.value = d.name;
      sel.appendChild(o);
    });
  }

  function applyFilters() {
    const q = $('#f-search').value.trim().toLowerCase();
    const sent = $('#f-sent').value;
    const src = $('#f-src').value;
    const cat1 = $('#f-cat1').value;
    const onlyDoubt = $('#f-doubt').checked;

    filtered = D.detail.filter(d => {
      if (sent && d.sent !== sent) return false;
      if (src && d.src !== src) return false;
      if (cat1 && d.c1 !== cat1) return false;
      if (onlyDoubt && !d.doubt) return false;
      if (q) {
        const hay = ((d.snip || '') + ' ' + (d.snip_zh || '') + ' ' + (d.c2 || '') + ' ' + (d.c1 || '') + ' ' + (d.raw || '') + ' ' + (d.raw_zh || '') + ' ' + (d.mode || '')).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
    renderDetail();
  }

  function renderDetail() {
    const tb = $('#detail-body');
    tb.innerHTML = '';
    $('#f-count').textContent = `显示 ${fmt(filtered.length)} / ${fmt(D.detail.length)} 条`;

    // 性能：一次拼接后写入
    const frag = document.createDocumentFragment();
    const LIMIT = filtered.length; // 全部渲染（2559 行可接受）
    filtered.slice(0, LIMIT).forEach(d => {
      const tr = el('tr', 'expandable');
      const snipZh = (d.snip_zh || '').trim();
      const snipEn = (d.snip || '').trim();
      const rawZh = (d.raw_zh || '').trim();
      const rawEn = (d.raw || '').trim();
      tr.innerHTML = `
        <td class="r" style="color:var(--text-mute)">${d.i}</td>
        <td class="snip">
          <div style="font-weight:500;color:var(--text)">${esc(snipZh || snipEn)}</div>
          ${snipZh && snipZh !== snipEn ? `<div style="font-size:11px;color:var(--text-mute);font-style:italic;margin-top:2px">${esc(snipEn)}</div>` : ''}
          <div class="raw-full">
            ${rawZh && rawZh !== rawEn ? `<div style="margin-bottom:3px">${esc(rawZh)}</div>` : ''}
            <div>${esc(rawEn)}</div>
          </div>
        </td>
        <td><span class="pill ${d.sent === '负面' ? 'neg' : d.sent === '正向' ? 'pos' : 'neu'}">${esc(d.sent)}</span></td>
        <td><span class="pill src">${esc(d.src === '买家之声退货报告' ? '退货报告' : '买家评论')}</span></td>
        <td>${esc(d.c1)}</td>
        <td style="color:var(--text-dim)">${esc(d.c2)}</td>
        <td>${(d.mode || d.c3) ? '<span class="pill" style="background:#e8f0fe;color:#1d4ed8;border:1px solid #c7dbfb;font-size:10.5px">' + esc(d.mode || d.c3) + '</span>' : '<span style="color:var(--text-mute);font-size:11px">—</span>'}</td>
        <td>${d.spec ? '有' : '<span style="color:var(--text-mute)">无</span>'}${
          d.doubt ? ' <span class="pill doubt" style="font-size:10px">存疑</span>' : ''}</td>`;
      tr.addEventListener('click', () => tr.classList.toggle('expanded'));
      frag.appendChild(tr);
    });
    tb.appendChild(frag);
  }

  /* ==========================================================================
     业务解读
     ========================================================================== */
  /* ==========================================================================
     业务解读：全部从数据推导，不写死任何品类结论
     ========================================================================== */
  function renderInsights() {
    const k = D.kpi;
    const negN = k.negN || 1;

    // 一级大类（负面）
    const cat1s = (D.cat1_neg || []).slice().sort((a, b) => b.n - a.n);
    const top1 = cat1s[0] || { name: '—', n: 0, pct: 0 };

    // 失效模式 Top（部件 × 模式）
    const modes = [];
    (D.dims || []).forEach(d => (d.modes || []).forEach(m => {
      modes.push({ part: d.dim, mode: m.mode, phen: m.phen || '', n: m.n,
                   pct: m.pct_of_neg, ret: m.ret, rev: m.rev });
    }));
    modes.sort((a, b) => b.n - a.n);
    const topModes = modes.filter(m => m.mode !== UNSPEC).slice(0, 3);
    const topPart = (D.dims || [])[0] || { dim: '—', n: 0, pct_of_neg: 0 };

    // 跨来源差异最大的一级大类（单一来源时无差异可言）
    const srcs = (D.src_cmp || []).slice().sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
    const twoSources = (k.ret_op > 0) && (k.rev_op > 0);
    const srcTop = srcs[0] || { name: '—', ret: 0, rev: 0, diff: 0 };

    // 普遍 vs 个案（由 cross 表给出）
    const cross = D.cross || [];
    const wide = cross.filter(c => c.kind === '普遍');
    const wideN = wide.reduce((s, c) => s + c.n, 0);

    const cards = [];

    cards.push({
      cls: 'red', icon: '⚠',
      title: '首要痛点：' + top1.name,
      body: [
        `共 <span class="hl">${fmt(top1.n)} 条</span>负面观点，占全部负面 <span class="hl">${pct(top1.pct)}</span>，
         是当前最集中的问题大类。`,
        `其下最大的具体失效模式是「<span class="hl">${esc(topModes[0] ? topModes[0].mode : '—')}</span>」
         （${fmt(topModes[0] ? topModes[0].n : 0)} 条，占全部负面 ${pct(topModes[0] ? topModes[0].pct : 0)}），
         落在部件「${esc(topModes[0] ? topModes[0].part : '—')}」。`
      ]
    });

    if (topModes.length >= 2) {
      cards.push({
        cls: 'red', icon: '◈',
        title: '失效模式 Top 3',
        body: [
          topModes.map(m => `「<span class="hl">${esc(m.mode)}</span>」${fmt(m.n)} 条
            （${pct(m.pct)}，${esc(m.part)}）`).join('；') + '。',
          `三者合计 ${fmt(topModes.reduce((s, m) => s + m.n, 0))} 条，
           占全部负面 ${pct(topModes.reduce((s, m) => s + m.pct, 0))}。`
        ]
      });
    }

    cards.push({
      cls: 'amber', icon: '◎',
      title: '部件集中度：' + topPart.dim,
      body: [
        `「${esc(topPart.dim)}」相关负面 <span class="hl">${fmt(topPart.n)} 条</span>，
         占全部负面 <span class="hl">${pct(topPart.pct_of_neg)}</span>，是最需要优先改动的部件。`,
        `该部件下细分出 ${fmt((topPart.modes || []).length)} 种失效模式，
         建议逐条确认是设计问题还是工艺问题。`
      ]
    });

    if (twoSources) {
      cards.push({
        cls: 'amber', icon: '⟳',
        title: '来源差异最大：' + srcTop.name,
        body: [
          `退货来源内部占比 <span class="hl">${pct(srcTop.ret)}</span>，
           评论来源内部占比 <span class="hl">${pct(srcTop.rev)}</span>，
           差 <span class="hl">${srcTop.diff > 0 ? '+' : ''}${srcTop.diff.toFixed(2)} 个百分点</span>。`,
          srcTop.diff >= 0
            ? `该问题在<b>退货人群</b>中更集中，说明评论星级会低估它的实际规模——
               收到货就用、发现不对就直接退货的人，不会写评论。`
            : `该问题在<b>评论人群</b>中更集中，说明它更像是「用了之后才暴露」的问题，
               退货人群未必会写进理由。`
        ]
      });
    } else {
      cards.push({
        cls: 'amber', icon: '⟳',
        title: '来源差异：本次数据不可比',
        body: [
          `本次仅包含<b>${k.ret_op > 0 ? '买家之声退货报告' : '买家评论'}</b>一个来源
           （${fmt(k.ret_op > 0 ? k.raw_ret : k.raw_rev)} 条原文），
           无法比较「退货人群 vs 评论人群」的痛点分布差异。`,
          `同时提供两个来源的数据后，这里会自动给出差异最大的问题大类。`
        ]
      });
    }

    if (wide.length) {
      cards.push({
        cls: 'red', icon: '▤',
        title: '普遍问题 vs 个案问题',
        body: [
          `判定为 <span class="hl">普遍</span>（≥3 条不同原文，或退货与评论双来源出现）的有
           <span class="hl">${fmt(wide.length)} 类</span>，共 ${fmt(wideN)} 条，
           占全部负面 ${pct(wideN / negN * 100)}——属于结构性问题，应优先立项。`,
          `其余为个案（偶发），建议先积累样本再判断。`
        ]
      });
    }

    cards.push({
      cls: 'green', icon: '✓',
      title: '样本局限（必须标注）',
      body: [
        `评论 <span class="hl">${fmt(k.raw_rev)} 条</span>（${fmt(k.rev_op)} 条观点，
         占全部观点 ${pct(k.rev_pct)}）`
        + (k.raw_ret > 0
          ? `；退货来源 <span class="hl">${fmt(k.raw_ret)} 条</span>，天然放大负面。`
          : `；本次<b>未包含退货报告</b>，无法覆盖「收货即退货」人群的问题。`),
        `另有 <span class="hl">${fmt(k.doubt)} 条</span>（${pct(k.doubt_pct)}）语义模糊已标记「归类存疑」，
         需人工复核。结论应作为 <span class="hl">改善假设的方向</span>，而非根因定论。`
      ]
    });

    const box = $('#insight-grid');
    box.innerHTML = '';
    cards.forEach(c => {
      const d = el('div', 'icard ' + c.cls);
      d.innerHTML = `<h4><span style="color:inherit">${c.icon}</span>${esc(c.title)}</h4>` +
        c.body.map(p => `<p>${p}</p>`).join('');
      box.appendChild(d);
    });

    // 章节说明与样本局限文案（数据驱动）
    const set = (id, v) => { const e = document.getElementById(id); if (e) e.innerHTML = v; };
    set('s6-ret', fmt(k.raw_ret));
    set('s6-rev', fmt(k.raw_rev));
    set('s6-limit',
      `<b>样本局限</b>：评论 ${fmt(k.raw_rev)} 条（${fmt(k.rev_op)} 条观点，占全部观点 ${pct(k.rev_pct)}）；
       退货数据来自「已退货人群」，天然放大负面。另有 ${fmt(k.doubt)} 条（${pct(k.doubt_pct)}）
       语义模糊已标记「归类存疑」，需人工复核。本报告结论应作为
       <b>改善假设的方向</b>，而非根因定论。`);
    set('f-ret', fmt(k.raw_ret));
    set('f-rev', fmt(k.raw_rev));
    set('f-total', fmt(k.total));
    set('f-date', '生成于 ' + (k.date || new Date().toISOString().slice(0, 10)));
    const mdate = document.getElementById('m-date');
    if (mdate) mdate.textContent = k.date || new Date().toISOString().slice(0, 10);
  }

  /* ---------------- 改善方向与优先级（数据驱动） ---------------- */
  function renderActions() {
    const negN = D.kpi.negN || 1;
    const cross = D.cross || [];
    const top = cross.filter(c => c.mode !== UNSPEC).slice()
      .sort((a, b) => b.score - a.score).slice(0, 6);

    const actions = top.map((c, i) => {
      const p = i === 0 ? 'P0' : i <= 2 ? 'P1' : i <= 4 ? 'P2' : 'P3';
      let body;
      if (c.cross_source) {
        body = `该问题在<b>退货报告与买家评论两个来源同时出现</b>（退货 ${fmt(c.ret)} 条 / 评论 ${fmt(c.rev)} 条），
                说明不是个别买家的主观感受，而是产品侧的共性问题。建议：① 复现该场景确认根因；
                ② 给出明确的修复方案与时间点；③ 在详情页补充边界说明，减少误购。`;
      } else if (c.kind === '普遍') {
        body = `该问题在单一来源中出现，但已涉及 <b>${fmt(c.docs)} 条不同买家原文</b>，具备普遍性。
                建议：① 归入产品需求池按部件（${esc(c.part)}）排期；
                ② 若短期内不能改，先在文案与包装上给出使用提示。`;
      } else {
        body = `该问题目前仅涉及 <b>${fmt(c.docs)} 条原文</b>，属于偶发个例。
                建议先继续观察，暂不投入改造资源；若后续样本增加则升级优先级。`;
      }
      return { p, dir: c.mode + '（' + c.part + '）', body, cov: c.pct };
    });

    const tb = $('#action-body');
    tb.innerHTML = '';
    if (!actions.length) {
      const tr = el('tr');
      tr.innerHTML = `<td colspan="4" style="color:var(--text-mute)">
        本次未识别到具体失效模式，无法生成行动建议（请检查 taxonomy 配置或补充 failure_modes）。</td>`;
      tb.appendChild(tr);
      return;
    }
    actions.forEach(a => {
      const tr = el('tr');
      const pc = a.p === 'P0' ? C.neg : a.p === 'P1' ? C.warn : C.neu;
      tr.innerHTML = `
        <td><span class="pill" style="background:${pc}22;color:${pc};border:1px solid ${pc}55">${a.p}</span></td>
        <td style="font-weight:600">${esc(a.dir)}</td>
        <td style="color:var(--text-dim);font-size:12px">${a.body}</td>
        <td class="r">${a.cov == null ? '<span style="color:var(--text-mute)">—</span>' : pct(a.cov)}</td>`;
      tb.appendChild(tr);
    });
  }

  /* ---------------- 来源差异信号（自动识别，不预设结论） ---------------- */
  function renderUniqueSignals() {
    const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    const setHtml = (id, v) => { const e = document.getElementById(id); if (e) e.innerHTML = v; };
    const rows = (D.src_cmp || []).slice();
    const k = D.kpi || {};
    const onlyOne = !(k.ret_op > 0) || !(k.rev_op > 0);

    if (onlyOne) {
      // 只有单一来源时，来源差异无从谈起 —— 不硬凑结论
      setHtml('sig1-title', '① 来源差异不可比');
      setHtml('sig1-name', '—');
      set('sig1-ret', '—');
      set('sig1-rev', '—');
      setHtml('sig1-note', '本次数据只包含<b>单一来源</b>（'
        + (k.ret_op > 0 ? '仅退货报告' : '仅买家评论')
        + '），无法比较两个来源的痛点分布差异。需要同时提供退货报告与评论才能得出该结论。');
      setHtml('sig2-title', '② 来源差异不可比');
      setHtml('sig2-name', '—');
      set('sig2-ret', '—');
      set('sig2-rev', '—');
      setHtml('sig2-note', '补充另一来源的数据后，此处会自动给出「哪个问题更偏向退货人群 / 更偏向评论人群」的对比。');
      return;
    }

    const byRet = rows.slice().sort((a, b) => b.ret - a.ret)[0];
    const byRev = rows.slice().sort((a, b) => b.rev - a.rev)[0];

    if (byRet) {
      setHtml('sig1-title', '① 退货来源占比最高的一级大类');
      set('sig1-name', byRet.name);
      set('sig1-ret', pct(byRet.ret));
      set('sig1-rev', pct(byRet.rev));
      setHtml('sig1-note', byRet.diff >= 0
        ? `在<b>退货人群</b>中更集中（差 ${byRet.diff.toFixed(2)} 个百分点）。
           收货即退货的用户不会写评论，因此<b>评论星级会低估这类问题的实际规模</b>。`
        : `在<b>评论人群</b>中更集中，属于「用了之后才暴露」的问题。`);
    }
    if (byRev) {
      setHtml('sig2-title', '② 评论来源占比最高的一级大类');
      set('sig2-name', byRev.name);
      set('sig2-ret', pct(byRev.ret));
      set('sig2-rev', pct(byRev.rev));
      setHtml('sig2-note', byRev.diff <= 0
        ? `在<b>评论人群</b>中更集中（差 ${Math.abs(byRev.diff).toFixed(2)} 个百分点）。
           这类问题退货人群未必写进理由，需要靠评论侧才能观察到。`
        : `在<b>退货人群</b>中更集中，说明该问题以「直接退货」的形式离开。`);
    }
  }

  /* ==========================================================================
     导航高亮
     ========================================================================== */
  function initNav() {
    const links = [...document.querySelectorAll('nav.anchor a')];
    const secs = links.map(a => document.querySelector(a.getAttribute('href')));

    const io = new IntersectionObserver(entries => {
      entries.forEach(en => {
        if (en.isIntersecting) {
          const i = secs.indexOf(en.target);
          if (i >= 0) {
            links.forEach(l => l.classList.remove('active'));
            links[i].classList.add('active');
          }
        }
      });
    }, { rootMargin: '-56px 0px -70% 0px', threshold: 0 });

    secs.forEach(s => s && io.observe(s));
  }

  /* ==========================================================================
     启动
     ========================================================================== */
  function init(data) {
    D = data;

    renderKpi();
    renderSentiment();
    renderSpecific();
    renderPie();
    renderTableCat1();
    renderTableCat2();
    renderSunburst();
    renderPainList();
    renderGrouped();
    renderDiff();
    fillCat1Select();
    applyFilters();
    renderUniqueSignals();
    renderL3Summary();
    renderDrill();
    renderInsights();
    renderActions();
    initNav();

    // 筛选事件
    ['#f-search', '#f-sent', '#f-src', '#f-cat1', '#f-doubt'].forEach(s => {
      const n = $(s);
      n.addEventListener(s === '#f-search' ? 'input' : 'change', applyFilters);
    });

    const boot = $('#boot');
    boot.classList.add('gone');
    setTimeout(() => boot.remove(), 450);
  }

  /* 数据加载：data.js 通过 <script> 注入 window.__INSIGHT_DATA__，
     file:// 与 http:// 下均可用，无 fetch / CORS 问题 */
  function load() {
    if (window.__INSIGHT_DATA__) {
      try {
        init(window.__INSIGHT_DATA__);
      } catch (err) {
        fail('数据渲染出错：' + err.message);
      }
      return;
    }
    fail('未能加载数据文件 data.js');
  }

  function fail(msg) {
    const boot = document.getElementById('boot');
    if (!boot) return;
    boot.innerHTML =
      '<div style="color:#b45309;font-size:14px;text-align:center;line-height:1.9">' +
      '⚠️ ' + msg + '<br>' +
      '<span style="color:#5a687c;font-size:12.5px">' +
      '请确认 data.js 与本页面在同一目录</span></div>';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
