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
  const fmt = n => (n == null ? '—' : n.toLocaleString('en-US'));
  const pct = n => (n == null ? '—' : n.toFixed(2) + '%');
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
      { name: '退货报告', n: k.ret_op },
      { name: '买家评论', n: k.rev_op }
    ];
    const colors2 = { '退货报告': C.negDeep, '买家评论': C.teal };
    donut('#chart-source', data2, {
      size: 160, thick: .38, centerTop: pct(k.rev_pct), centerBot: '评论占比',
      colors: colors2, labelMin: 20
    });

    // 退货来源具象率
    const retSpec = D.detail.filter(d => d.src === '买家之声退货报告');
    const rp = retSpec.filter(d => d.spec).length / retSpec.length * 100;
    $('#ret-spec-rate').textContent = pct(rp);
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
      const pname = d.mode || d.name || "—";
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
  function renderInsights() {
    const k = D.kpi;
    const negN = k.negN;
    // 从数据取值，避免硬编码漂移
    const g = n => D.neg_tree.find(x => x.name === n) || { n: 0, pct: 0, children: [] };
    const sub = (n) => {
      for (const grp of D.neg_tree) {
        const c = grp.children.find(x => x.name === n);
        if (c) return c;
      }
      return { n: 0, pct_in_cat1: 0, pct_of_neg: 0 };
    };
    const gListing = g('Listing预期不符');
    const gMaterial = g('产品做工&材质');
    const gStruct = g('结构/功能配件');
    const gShip = g('包装物流');
    const sPlate = sub('与描述预期不符（平台理由·泛称）');
    const sThin = sub('材质单薄/廉价感（感知做工）');
    const sBroke = sub('易断裂/破损（结构脆弱）');
    const sHinge = sub('铰链/中轴区域无防护');
    const sStand = sub('支架/指环功能失效');
    const sScreen = sub('屏幕保护膜/前盖不兼容');
    const sMag = sub('磁吸/无线充电不兼容');
    const srcRow = n => D.src_cmp.find(x => x.name === n) || { ret: 0, rev: 0, diff: 0 };
    const rListing = srcRow('Listing预期不符');
    const rShip = srcRow('包装物流');

    const cards = [
      {
        cls: 'red', icon: '⚠', title: 'Listing 预期管理失效（第一痛点）',
        body: [`共 <span class="hl">${fmt(gListing.n)} 条</span>，占全部负面 <span class="hl">${pct(gListing.pct)}</span>。
                其中「与描述预期不符（平台理由·泛称）」<span class="hl">${fmt(sPlate.n)} 条</span>，
                占该大类 ${pct(sPlate.pct_in_cat1)}。`,
               `退货来源 ${pct(rListing.ret)} vs 评论来源 ${pct(rListing.rev)}，
                差 <span class="hl">${rListing.diff > 0 ? '+' : ''}${rListing.diff.toFixed(2)} 个百分点</span>。
                问题发生在「购买前的预期形成」环节，而非使用后的口碑环节。`]
      },
      {
        cls: 'red', icon: '◈', title: '材质单薄与结构脆弱',
        body: [`共 <span class="hl">${fmt(gMaterial.n)} 条</span>，占全部负面 <span class="hl">${pct(gMaterial.pct)}</span>。
                「材质单薄/廉价感」${fmt(sThin.n)} 条（占该大类 ${pct(sThin.pct_in_cat1)}）、
                「易断裂/破损」${fmt(sBroke.n)} 条（${pct(sBroke.pct_in_cat1)}），
                两者合计 <span class="hl">${pct(sThin.pct_in_cat1 + sBroke.pct_in_cat1)}</span>。`,
               `本质是「薄壳轻量化」定位与「折叠屏高价设备需强防护」的用户预期之间的冲突。`]
      },
      {
        cls: 'amber', icon: '◎', title: '铰链/中轴无防护',
        body: [`共 <span class="hl">${fmt(sHinge.n)} 条</span>，是「结构/功能配件」下第一大二级痛点，
                占该大类 <span class="hl">${pct(sHinge.pct_in_cat1)}</span>。`,
               `大量表述为「以为是有的、结果没有」（如 "thought it had hinge protection"），
                说明这不只是产品缺配，更是 <span class="hl">信息未披露</span>。`]
      },
      {
        cls: 'red', icon: '⟳', title: '配件功能可靠性',
        body: [`支架/指环失效 <span class="hl">${fmt(sStand.n)} 条</span>（占结构类 ${pct(sStand.pct_in_cat1)}）、
                贴膜不兼容 <span class="hl">${fmt(sScreen.n)} 条</span>（${pct(sScreen.pct_in_cat1)}）、
                磁吸充电不兼容 <span class="hl">${fmt(sMag.n)} 条</span>（${pct(sMag.pct_in_cat1)}）。`,
               `这三项是评论侧最集中的吐槽：都是「要用一段时间才暴露」的问题。`]
      },
      {
        cls: 'amber', icon: '▤', title: '包装/物流破损',
        body: [`退货来源 <span class="hl">${pct(rShip.ret)}</span>（到货破损 + 配件缺失/错发），
                评论来源 <span class="hl">${pct(rShip.rev)}</span>。`,
               `收到破损包裹的用户直接退货、不写评论，因此
                <span class="hl">评论星级低估了到货质量问题的规模</span>。`]
      },
      {
        cls: 'green', icon: '✓', title: '样本局限（必须标注）',
        body: [`评论仅 <span class="hl">${fmt(k.raw_rev)} 条</span>（${fmt(k.rev_op)} 条观点，占全部观点 ${pct(k.rev_pct)}），
                不足以代表整体口碑；退货数据来自「已退货人群」，天然放大负面。`,
               `另有 <span class="hl">${fmt(k.doubt)} 条</span>（${pct(k.doubt_pct)}）语义模糊已标记「归类存疑」，需人工复核。
                结论应作为 <span class="hl">改善假设的方向</span>，而非根因定论。`]
      }
    ];

    const box = $('#insight-grid');
    box.innerHTML = '';
    cards.forEach(c => {
      const d = el('div', 'icard ' + c.cls);
      d.innerHTML = `<h4><span style="color:inherit">${c.icon}</span>${esc(c.title)}</h4>` +
        c.body.map(p => `<p>${p}</p>`).join('');
      box.appendChild(d);
    });
  }

  function renderActions() {
    const negN = D.kpi.negN;
    const subN = (n) => {
      for (const grp of D.neg_tree) {
        const c = grp.children.find(x => x.name === n);
        if (c) return c.n;
      }
      return 0;
    };
    const grpN = (n) => (D.neg_tree.find(x => x.name === n) || { n: 0 }).n;
    const p = n => n / negN * 100;

    const covListing = p(grpN('Listing预期不符') + subN('尺寸/机型不适配'));
    const covStruct = p(subN('易断裂/破损（结构脆弱）') + subN('材质单薄/廉价感（感知做工）'));
    const covHinge = p(subN('铰链/中轴区域无防护'));
    const covShip = p(grpN('包装物流'));

    const actions = [
      {
        p: 'P0', dir: 'Listing 前置披露',
        body: '① 主图/视频明确标注「本款不含铰链保护」，A+ 页对比含/不含铰链护盖两条产品线；' +
              '② 补上「360° 旋转磁吸支架」「兼容 MagSafe 充电」的真实边界条件；' +
              '③ 删除/弱化「military grade / full protection」等易被判虚假宣传的表述；' +
              '④ 增加机型适配对照表。',
        cov: covListing
      },
      {
        p: 'P0', dir: '结构可靠性专项',
        body: '① 中框与铰链侧壁加厚/加筋，解决「易断裂」；② 支架转轴改阻尼+金属件；' +
              '③ 前盖与贴膜配合公差重做；④ 磁吸环位置与厚度复核。',
        cov: covStruct
      },
      {
        p: 'P1', dir: '铰链防护产品线',
        body: '该品类存在明确的「要防护」需求（评论侧亦有提及），建议单独开发含中轴护盖的 SKU，' +
              '与现款轻薄线并行，而非二选一。',
        cov: covHinge
      },
      {
        p: 'P1', dir: '包装与到货质量',
        body: '加固外箱抗压、增加内衬固定；把屏幕保护膜/钢化膜列入出货清单核对项。',
        cov: covShip
      },
      {
        p: 'P2', dir: '评论侧运营',
        body: '对已退货用户定向回访；对高星评价做追问式引导（邀请描述握持手感、支架使用场景），' +
              '把「用了才知道」的功能问题提前暴露在评论中，补足评论样本。',
        cov: null
      }
    ];

    const tb = $('#action-body');
    tb.innerHTML = '';
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

  /* ---------------- 退货独有信号（动态填充） ---------------- */
  function renderUniqueSignals() {
    const get = n => D.src_cmp.find(x => x.name === n) || { ret: 0, rev: 0, diff: 0 };
    const l = get('Listing预期不符');
    const sh = get('包装物流');
    const subN = n => {
      for (const grp of D.neg_tree) {
        const c = grp.children.find(x => x.name === n);
        if (c) return c.n;
      }
      return 0;
    };
    const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };

    set('uniq-l-ret', pct(l.ret));
    set('uniq-l-rev', pct(l.rev));
    set('uniq-l-diff', (l.diff > 0 ? '+' : '') + l.diff.toFixed(2) + ' 个百分点');

    set('sig1-ret', pct(l.ret));
    set('sig1-rev', pct(l.rev));

    set('sig2-ret', pct(sh.ret));
    set('sig2-rev', sh.rev > 0 ? pct(sh.rev) : '0 条');
    set('sig2-broke', fmt(subN('到货已破损（平台理由·未指明部位）')));
    set('sig2-miss', fmt(subN('包装/配件缺失或错发')));
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
