// ============================================================
//  Gangtise Dashboard Charts  –  charts.js
//  Supports 5 sections: funnel | channel | kol | revenue | segment
//  Lazy rendering: each section renders once on first visit
// ============================================================

function themeVar(name, fallback) {
  const value = getComputedStyle(document.body).getPropertyValue(name).trim();
  return value || fallback;
}

function currentPalette() {
  return {
    gold: themeVar('--gold', '#C8A96E'),
    goldLight: themeVar('--gold-light', '#E2C98A'),
    goldDark: themeVar('--gold-dark', '#A8893E'),
    navy: themeVar('--navy', '#0D1B2A'),
    navyMid: themeVar('--navy-mid', '#1A2E45'),
    white: themeVar('--white', '#F8F6F0'),
    gray: themeVar('--gray-400', '#9A9590'),
    green: '#2ECC71',
    red: '#E74C3C',
    blue: '#3498DB',
  };
}

let GOLD = '#C8A96E';
let GOLD_LIGHT = '#E2C98A';
let GOLD_DARK = '#A8893E';
let NAVY = '#0D1B2A';
let NAVY_MID = '#1A2E45';
let WHITE = '#F8F6F0';
let GRAY = '#9A9590';
let GREEN = '#2ECC71';
let RED = '#E74C3C';
let BLUE = '#3498DB';

function refreshPalette() {
  const palette = currentPalette();
  GOLD = palette.gold;
  GOLD_LIGHT = palette.goldLight;
  GOLD_DARK = palette.goldDark;
  NAVY = palette.navy;
  NAVY_MID = palette.navyMid;
  WHITE = palette.white;
  GRAY = palette.gray;
  GREEN = palette.green;
  RED = palette.red;
  BLUE = palette.blue;
}

function updateChartDefaults() {
  refreshPalette();
  Chart.defaults.color = GRAY;
  Chart.defaults.borderColor = 'rgba(200,169,110,0.08)';
  Chart.defaults.font.family = "'PingFang SC', 'Microsoft YaHei', sans-serif";
}

const CHANNEL_COLORS  = ['#07C160', '#FE2C55', '#FF2442', '#E6162D', '#C8A96E'];
const SEGMENT_COLORS  = ['#4A5568', '#3182CE', '#38A169', '#C8A96E', '#FFD700'];
const TIER_COLORS     = ['#4A5568', '#3182CE', '#38A169', '#C8A96E'];

updateChartDefaults();

// Track which sections have been rendered
const renderedSections = new Set();
const chartRegistry = [];

function registerChart(chart) {
  chartRegistry.push(chart);
  return chart;
}

function destroyRegisteredCharts() {
  while (chartRegistry.length) {
    const chart = chartRegistry.pop();
    if (chart && typeof chart.destroy === 'function') chart.destroy();
  }
}

function createChart(ctx, config) {
  const existing = Chart.getChart(ctx);
  if (existing) existing.destroy();
  return registerChart(new Chart(ctx, config));
}

// ============================================================
//  SECTION NAVIGATION
// ============================================================
const SECTION_TITLES = {
  funnel:  '多渠道多圈层转化分析',
  channel: '渠道分析',
  kol:     '作者协同效能分析',
  revenue: '营收趋势',
  segment: '用户分层分析',
};

function showDashSection(section) {
  // Update nav active state
  document.querySelectorAll('[id^="nav-"]').forEach(el => el.classList.remove('active'));
  const navEl = document.getElementById('nav-' + section);
  if (navEl) navEl.classList.add('active');

  // Show/hide sections
  document.querySelectorAll('.dash-section').forEach(el => el.classList.remove('active'));
  const secEl = document.getElementById('ds-' + section);
  if (secEl) secEl.classList.add('active');

  // Update topbar title
  const titleEl = document.getElementById('topbar-title');
  if (titleEl) titleEl.textContent = SECTION_TITLES[section] || '';

  // Lazy render
  if (!renderedSections.has(section)) {
    renderedSections.add(section);
    renderSection(section);
  }
}

function getActiveDashSection() {
  const active = document.querySelector('.dash-section.active');
  return active ? active.id.replace('ds-', '') : null;
}

function rerenderDashboardSection(section) {
  updateChartDefaults();
  destroyRegisteredCharts();
  renderedSections.clear();
  if (document.getElementById('ds-' + section)) {
    showDashSection(section);
  }
}

function initDashboardCharts(initialSection) {
  const section = initialSection || getActiveDashSection() || 'funnel';
  rerenderDashboardSection(section);
}

function renderSection(section) {
  switch (section) {
    case 'funnel':  renderFunnelSection();  break;
    case 'channel': renderChannelSection(); break;
    case 'kol':     renderKolSection();     break;
    case 'revenue': renderRevenueSection(); break;
    case 'segment': renderSegmentSection(); break;
  }
}

// ---- Date filter (UI only) ----
function setDateRange(btn, range) {
  document.querySelectorAll('.date-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

// ============================================================
//  HELPERS
// ============================================================
function fmtWan(n) { return (n / 10000).toFixed(1) + '万'; }
function fmtMoney(n) { return '¥' + fmtWan(n); }

function makeTooltipOptions(extra) {
  const palette = currentPalette();
  return Object.assign({ backgroundColor: palette.navyMid, borderColor: palette.gold, borderWidth: 1 }, extra || {});
}

function donutLegendPosition(ctx) {
  const container = ctx && ctx.parentElement;
  const width = container ? container.clientWidth : window.innerWidth;
  return width <= 420 ? 'bottom' : 'right';
}

// ============================================================
//  SECTION 1: 转化漏斗  (Funnel)
// ============================================================
async function renderFunnelSection() {
  await Promise.all([
    renderFunnel(),
    renderChannelDonut(),
    renderRevenueTrend(),
    renderKolBar(),
    renderSegmentDonut(),
    renderChannelRevenue(),
    renderHeatmap(),
  ]);
}

// --- Funnel bars (HTML) ---
async function renderFunnel() {
  const res  = await fetch('/api/funnel');
  const data = await res.json();
  const container = document.getElementById('funnel-container');
  if (!container) return;
  const maxCount = data[0].count;
  const minWidthPct = 32;
  container.innerHTML = data.map((item, i) => {
    const widthPct  = Math.round((item.count / maxCount) * 100);
    const dropRate  = i > 0 ? ((data[i-1].count - item.count) / data[i-1].count * 100).toFixed(1) : null;
    const stageWidth = Math.max(widthPct, minWidthPct);
    return `
      <div class="funnel-stage-group">
        <div class="funnel-stage" style="width:${stageWidth}%">
          <div class="funnel-stage-box">
            <div class="funnel-stage-title">${item.layer}</div>
            <div class="funnel-stage-stats">
              <span class="funnel-stage-count">${(item.count/10000).toFixed(1)}万</span>
              <span class="funnel-stage-share">${item.rate.toFixed(1)}%</span>
            </div>
          </div>
        </div>
        <div class="funnel-stage-conv ${dropRate ? '' : 'funnel-stage-conv-base'}">${dropRate ? '↓ 较上一层流失 ' + dropRate + '%' : '验证起点'}</div>
      </div>`;
  }).join('');
}

// --- Channel donut ---
async function renderChannelDonut() {
  const res  = await fetch('/api/channels');
  const data = await res.json();
  const ctx  = document.getElementById('channelDonut');
  if (!ctx) return;
  createChart(ctx, {
    type: 'doughnut',
    data: {
      labels: data.map(d => d.name),
      datasets: [{
        data: data.map(d => d.users),
        backgroundColor: CHANNEL_COLORS,
        borderColor: NAVY_MID,
        borderWidth: 3,
        hoverOffset: 8,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '65%',
      plugins: {
        legend: {
          position: donutLegendPosition(ctx),
          labels: { color: WHITE, font: { size: 12 }, padding: 12, boxWidth: 12 }
        },
        tooltip: { callbacks: { label: c => ` ${c.label}: ${c.raw} 留资用户` } }
      }
    }
  });
}

// --- Revenue trend (dual axis) ---
async function renderRevenueTrend() {
  const res  = await fetch('/api/revenue');
  const data = await res.json();
  const ctx  = document.getElementById('revenueTrend');
  if (!ctx) return;
  createChart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.month.slice(5)),
      datasets: [
        {
          label: 'MRR (元)',
          data: data.map(d => d.revenue),
          backgroundColor: 'rgba(200,169,110,0.7)',
          borderColor: GOLD, borderWidth: 1, borderRadius: 4, yAxisID: 'y',
        },
        {
          label: '激活试用用户',
          data: data.map(d => d.users),
          type: 'line', borderColor: BLUE, backgroundColor: 'rgba(52,152,219,0.1)',
          borderWidth: 2, pointRadius: 3, pointBackgroundColor: BLUE,
          fill: true, tension: 0.4, yAxisID: 'y1',
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: WHITE, font: { size: 12 } } },
        tooltip: makeTooltipOptions()
      },
      scales: {
        x:  { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY } },
        y:  { position: 'left',  grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v } },
        y1: { position: 'right', grid: { drawOnChartArea: false },           ticks: { color: BLUE,  callback: v => v } }
      }
    }
  });
}

// --- KOL top5 horizontal bar ---
async function renderKolBar() {
  const res  = await fetch('/api/kols');
  const data = await res.json();
  const ctx  = document.getElementById('kolBar');
  if (!ctx) return;
  createChart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.name),
      datasets: [
        {
          label: '协同收入 (元)',
          data: data.map(d => d.gmv),
          backgroundColor: data.map((_, i) => i < 2 ? GOLD : 'rgba(200,169,110,0.4)'),
          borderColor: GOLD, borderWidth: 1, borderRadius: 4,
        },
        {
          label: '佣金 (元)',
          data: data.map(d => d.commission),
          backgroundColor: 'rgba(52,152,219,0.6)',
          borderColor: BLUE, borderWidth: 1, borderRadius: 4,
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: {
        legend: { labels: { color: WHITE, font: { size: 12 } } },
          tooltip: makeTooltipOptions({ callbacks: { label: c => ` ${c.dataset.label}: ¥${c.raw}` } })
      },
      scales: {
        x: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v } },
        y: { grid: { display: false }, ticks: { color: WHITE } }
      }
    }
  });
}

// --- Segment donut ---
async function renderSegmentDonut() {
  const res    = await fetch('/api/segments');
  const data   = await res.json();
  const ctx    = document.getElementById('segmentDonut');
  if (!ctx) return;
  createChart(ctx, {
    type: 'doughnut',
    data: {
      labels: data.map(d => d.segment),
      datasets: [{ data: data.map(d => d.count), backgroundColor: SEGMENT_COLORS, borderColor: NAVY_MID, borderWidth: 3, hoverOffset: 6 }]
    },
    options: { responsive: true, maintainAspectRatio: false, cutout: '60%', plugins: { legend: { display: false } } }
  });
  const legend = document.getElementById('segment-legend');
  if (legend) {
    legend.innerHTML = data.map((d, i) => `
      <div class="segment-item">
        <div class="segment-dot" style="background:${SEGMENT_COLORS[i]}"></div>
        <div class="segment-name">${d.segment}</div>
        <div class="segment-pct">${d.pct}%</div>
      </div>`).join('');
  }
}

// --- Channel revenue bar ---
async function renderChannelRevenue() {
  const res  = await fetch('/api/channels');
  const data = await res.json();
  const ctx  = document.getElementById('channelRevenue');
  if (!ctx) return;
  createChart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.name),
      datasets: [{ label: '月度营收 (元)', data: data.map(d => d.revenue), backgroundColor: CHANNEL_COLORS.map(c => c+'CC'), borderColor: CHANNEL_COLORS, borderWidth: 1, borderRadius: 6 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: makeTooltipOptions({ callbacks: { label: c => ` ¥${c.raw}` } }) },
      scales: {
        x: { grid: { display: false }, ticks: { color: GRAY } },
        y: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v } }
      }
    }
  });
}

// --- Heatmap table ---
async function renderHeatmap() {
  const channels = ['微信社群', '内容合作', '小红书', '转介绍', '直接流量'];
  const matrix   = [
    [100, 12.0, 3.2, 0.9, 0.3],
    [100, 10.4, 2.7, 1.0, 0.28],
    [100, 8.1, 2.1, 0.7, 0.19],
    [100, 16.5, 4.4, 1.6, 0.52],
    [100, 18.0, 5.1, 2.4, 0.9],
  ];
  const tbody = document.getElementById('heatmap-body');
  if (!tbody) return;
  tbody.innerHTML = channels.map((ch, i) => `
    <tr>
      <td style="color:var(--white);font-weight:500">${ch}</td>
      ${matrix[i].map((v, j) => {
        const intensity = j === 0 ? 0.08 : Math.min(v / (j===1 ? 45 : j===2 ? 15 : j===3 ? 10 : 2.5), 1);
        const bg        = `rgba(200,169,110,${(intensity * 0.6 + 0.05).toFixed(2)})`;
        const color     = intensity > 0.5 ? '#0D1B2A' : '#F8F6F0';
        return `<td style="background:${bg};color:${color};font-weight:${intensity>0.4?'600':'400'};text-align:center">${v}%</td>`;
      }).join('')}
    </tr>`).join('');
}


// ============================================================
//  SECTION 2: 渠道分析  (Channel)
// ============================================================
const CHANNEL_DATA = [
  { name: '微信社群', users: 2100, convRate: '6.4%', revenue: 28600, cac: 42, ltv: 620, score: 82, trend: '▲', trendCls: 'trend-up' },
  { name: '内容合作', users: 1400, convRate: '4.8%', revenue: 19200, cac: 56, ltv: 540, score: 74, trend: '▲', trendCls: 'trend-up' },
  { name: '小红书', users: 980, convRate: '3.6%', revenue: 13600, cac: 48, ltv: 420, score: 68, trend: '▲', trendCls: 'trend-up' },
  { name: '转介绍', users: 620, convRate: '12.1%', revenue: 24800, cac: 18, ltv: 860, score: 93, trend: '▲', trendCls: 'trend-up' },
  { name: '直接流量', users: 300, convRate: '15.0%', revenue: 16800, cac: 12, ltv: 940, score: 96, trend: '▲', trendCls: 'trend-up' },
];

const MONTHS_12 = ['2025-07','2025-08','2025-09','2025-10','2025-11','2025-12','2026-01','2026-02','2026-03','2026-04','2026-05','2026-06'];
const MONTHS_12_LABEL = MONTHS_12.map(m => m.slice(5)+'月');

// Monthly channel acquisition (stacked bar data, in thousands)
const CHANNEL_MONTHLY = [
  [120, 136, 148, 165, 172, 186, 194, 201, 214, 228, 241, 252],
  [82, 88, 94, 102, 110, 118, 126, 132, 139, 148, 156, 164],
  [56, 62, 68, 72, 79, 84, 88, 93, 96, 102, 108, 112],
  [28, 34, 38, 42, 45, 48, 52, 56, 60, 64, 68, 72],
  [12, 16, 18, 20, 23, 24, 26, 29, 31, 34, 36, 39],
];

function renderChannelSection() {
  // KPI cards
  const kpiContainer = document.getElementById('channel-kpi-cards');
  if (kpiContainer) {
    kpiContainer.innerHTML = CHANNEL_DATA.map(ch => `
      <div class="kpi-card">
        <div class="kpi-label">${ch.name}</div>
        <div class="kpi-value" style="font-size:20px">${ch.users}</div>
        <div class="kpi-sub">转化率 ${ch.convRate}</div>
        <div class="kpi-sub">营收 ¥${ch.revenue}</div>
        <div class="kpi-badge ${ch.trendCls === 'trend-up' ? 'kpi-badge-up' : 'kpi-badge-down'}">
          CAC ¥${ch.cac} · LTV ¥${ch.ltv}
        </div>
      </div>`).join('');
  }

  // Stacked bar – channel monthly acquisition
  const ctxStack = document.getElementById('channelStackedBar');
  if (ctxStack) {
    createChart(ctxStack, {
      type: 'bar',
      data: {
        labels: MONTHS_12_LABEL,
        datasets: CHANNEL_DATA.map((ch, i) => ({
          label: ch.name,
          data: CHANNEL_MONTHLY[i],
          backgroundColor: CHANNEL_COLORS[i] + 'CC',
          borderColor: CHANNEL_COLORS[i],
          borderWidth: 1,
          borderRadius: 2,
        }))
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: WHITE, font: { size: 11 }, boxWidth: 10, padding: 10 } },
          tooltip: makeTooltipOptions()
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: GRAY } },
          y: { stacked: true, grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => v } }
        }
      }
    });
  }

  // Scatter / Bubble – CAC vs LTV
  const ctxScatter = document.getElementById('cacLtvScatter');
  if (ctxScatter) {
    createChart(ctxScatter, {
      type: 'bubble',
      data: {
        datasets: CHANNEL_DATA.map((ch, i) => ({
          label: ch.name,
          data: [{ x: ch.cac, y: ch.ltv, r: Math.max(Math.sqrt(ch.users / 20), 6) }],
          backgroundColor: CHANNEL_COLORS[i] + '99',
          borderColor: CHANNEL_COLORS[i],
          borderWidth: 2,
        }))
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: WHITE, font: { size: 11 }, boxWidth: 10, padding: 10 } },
          tooltip: makeTooltipOptions({
            callbacks: {
              label: c => ` ${c.dataset.label}  CAC:¥${c.raw.x}  LTV:¥${c.raw.y}`
            }
          })
        },
        scales: {
          x: {
            title: { display: true, text: 'CAC (¥)', color: GRAY },
            grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY }
          },
          y: {
            title: { display: true, text: 'LTV (¥)', color: GRAY },
            grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY }
          }
        }
      }
    });
  }

  // Quality table
  const tbody = document.getElementById('channel-quality-body');
  if (tbody) {
    tbody.innerHTML = CHANNEL_DATA.map(ch => {
      const barW = Math.round(ch.score * 0.8);
      return `<tr>
        <td style="color:var(--white);font-weight:500">${ch.name}</td>
        <td>${ch.users}</td>
        <td>¥${ch.cac}</td>
        <td>¥${ch.ltv}</td>
        <td>${ch.convRate}</td>
        <td>
          <span class="score-bar" style="width:${barW}px"></span>
          <span style="color:var(--gold);font-weight:600">${ch.score}</span>
        </td>
        <td class="${ch.trendCls}">${ch.trend}</td>
      </tr>`;
    }).join('');
  }
}


// ============================================================
//  SECTION 3: 作者协同效能
// ============================================================
const KOL_TOP10 = [
  { name: '财经老王', platform: '微信', fans: '12.8万', gmv: 18600, commission: 2790, rate: '15%', tier: 'S', trend: '+12%' },
  { name: '投研精选', platform: '内容合作', fans: '8.6万', gmv: 14200, commission: 2130, rate: '15%', tier: 'S', trend: '+9%' },
  { name: '量化阿杰', platform: '小红书', fans: '5.4万', gmv: 11800, commission: 1770, rate: '15%', tier: 'A', trend: '+8%' },
  { name: '宏观视野', platform: '微信', fans: '4.2万', gmv: 9600, commission: 1536, rate: '16%', tier: 'A', trend: '+6%' },
  { name: '策略研究员', platform: '转介绍', fans: '3.1万', gmv: 7800, commission: 1170, rate: '15%', tier: 'A', trend: '+4%' },
  { name: '行业深度', platform: '内容合作', fans: '2.6万', gmv: 6200, commission: 930, rate: '15%', tier: 'B', trend: '+3%' },
  { name: '晨会纪要', platform: '小红书', fans: '2.1万', gmv: 5400, commission: 810, rate: '15%', tier: 'B', trend: '+2%' },
  { name: '大盘解读', platform: '微信', fans: '1.8万', gmv: 4600, commission: 690, rate: '15%', tier: 'B', trend: '+1%' },
  { name: '板块追踪', platform: '内容合作', fans: '1.5万', gmv: 3900, commission: 585, rate: '15%', tier: 'B', trend: '+1%' },
  { name: '新能源专研', platform: '小红书', fans: '1.2万', gmv: 3200, commission: 480, rate: '15%', tier: 'B', trend: '+1%' },
];

const KOL_TIER_GROWTH = {
  S: [1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2],
  A: [2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 5],
  B: [3, 3, 4, 4, 5, 5, 6, 7, 7, 8, 9, 10],
};

function renderKolSection() {
  // KPI cards
  const kpiContainer = document.getElementById('kol-kpi-cards');
  if (kpiContainer) {
    const totalGmv = KOL_TOP10.reduce((s, k) => s + k.gmv, 0);
    const totalKols = 12;
    const avgRate = '15.3%';
    const topKol = KOL_TOP10[0].name;
    kpiContainer.innerHTML = `
      <div class="kpi-card">
        <div class="kpi-label">试点作者总数</div>
        <div class="kpi-value">${totalKols}</div>
        <div class="kpi-badge kpi-badge-up">▲ +14 本月</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">试点协同收入</div>
        <div class="kpi-value">¥${totalGmv}</div>
        <div class="kpi-badge kpi-badge-up">▲ +22%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">平均佣金率</div>
        <div class="kpi-value">${avgRate}</div>
        <div class="kpi-badge kpi-badge-gold">加权平均</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">当前最佳样本</div>
        <div class="kpi-value" style="font-size:18px">${topKol}</div>
        <div class="kpi-badge kpi-badge-gold">种子作者</div>
      </div>`;
  }

  // Top 10 horizontal bar
  const ctxTop10 = document.getElementById('kolTop10Bar');
  if (ctxTop10) {
    createChart(ctxTop10, {
      type: 'bar',
      data: {
        labels: KOL_TOP10.map(k => k.name),
        datasets: [
          {
            label: '试点收入 (元)',
            data: KOL_TOP10.map(k => k.gmv),
            backgroundColor: KOL_TOP10.map((k, i) => {
              if (k.tier === 'S') return '#FFD700CC';
              if (k.tier === 'A') return GOLD + 'CC';
              return 'rgba(90,86,80,0.6)';
            }),
            borderColor: KOL_TOP10.map(k => k.tier === 'S' ? '#FFD700' : k.tier === 'A' ? GOLD : GRAY),
            borderWidth: 1,
            borderRadius: 4,
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false, indexAxis: 'y',
        plugins: {
          legend: { display: false },
          tooltip: makeTooltipOptions({ callbacks: { label: c => ` 收入: ¥${c.raw}` } })
        },
        scales: {
          x: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v } },
          y: { grid: { display: false }, ticks: { color: WHITE, font: { size: 11 } } }
        }
      }
    });
  }

  // Tier growth line chart
  const ctxTierGrowth = document.getElementById('kolTierGrowth');
  if (ctxTierGrowth) {
    createChart(ctxTierGrowth, {
      type: 'line',
      data: {
        labels: MONTHS_12_LABEL,
        datasets: [
          { label: 'S级', data: KOL_TIER_GROWTH.S, borderColor: '#FFD700', backgroundColor: 'rgba(255,215,0,0.08)', borderWidth: 2, pointRadius: 4, pointBackgroundColor: '#FFD700', tension: 0.4, fill: true },
          { label: 'A级', data: KOL_TIER_GROWTH.A, borderColor: GOLD,     backgroundColor: 'rgba(200,169,110,0.08)', borderWidth: 2, pointRadius: 4, pointBackgroundColor: GOLD,     tension: 0.4, fill: true },
          { label: 'B级', data: KOL_TIER_GROWTH.B, borderColor: GRAY,     backgroundColor: 'rgba(154,149,144,0.08)', borderWidth: 2, pointRadius: 4, pointBackgroundColor: GRAY,     tension: 0.4, fill: true },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: WHITE, font: { size: 12 } } }, tooltip: makeTooltipOptions() },
        scales: {
          x: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY } },
          y: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY } }
        }
      }
    });
  }

  // Tier donut
  const ctxTierDonut = document.getElementById('kolTierDonut');
  if (ctxTierDonut) {
    createChart(ctxTierDonut, {
      type: 'doughnut',
      data: {
        labels: ['S级', 'A级', 'B级'],
        datasets: [{
          data: [2, 5, 10],
          backgroundColor: ['#FFD700CC', GOLD+'CC', 'rgba(90,86,80,0.7)'],
          borderColor: ['#FFD700', GOLD, GRAY],
          borderWidth: 2,
          hoverOffset: 8,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '62%',
        plugins: { legend: { position: 'right', labels: { color: WHITE, font: { size: 12 }, padding: 16, boxWidth: 12 } } }
      }
    });
  }

  // KOL table
  const kolBody = document.getElementById('kol-table-body');
  if (kolBody) {
    kolBody.innerHTML = KOL_TOP10.slice(0, 8).map(k => {
      const tierCls = k.tier === 'S' ? 'kol-tier-s' : k.tier === 'A' ? 'kol-tier-a' : 'kol-tier-b';
      const trendColor = k.trend.startsWith('+') ? '#2ECC71' : '#E74C3C';
      return `<tr>
        <td style="color:var(--white);font-weight:500">${k.name}</td>
        <td>${k.platform}</td>
        <td>${k.fans}</td>
        <td style="color:var(--gold);font-weight:600">¥${k.gmv}</td>
        <td>${k.rate}</td>
        <td><span class="${tierCls}">${k.tier}级</span></td>
        <td style="color:${trendColor}">${k.trend}</td>
      </tr>`;
    }).join('');
  }
}


// ============================================================
//  SECTION 4: 营收趋势  (Revenue)
// ============================================================
const REVENUE_MONTHLY = [18000, 22400, 26800, 31200, 35600, 40200, 44800, 49200, 53800, 58600, 63400, 68800];
const USERS_MONTHLY   = [180, 238, 286, 332, 388, 446, 504, 566, 628, 688, 742, 806];

const TIER_REVENUE = {
  '免费':   [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  '验证版会员': [6200, 7400, 8600, 9800, 11200, 12600, 13800, 15100, 16200, 17400, 18600, 19800],
  '专业会员': [8400, 10800, 13200, 15400, 17600, 19800, 22400, 24600, 27200, 29600, 32200, 34800],
  '机构试点':  [3400, 4200, 5000, 6000, 6800, 7800, 8600, 9500, 10400, 11600, 12600, 14000],
};

const COHORT_DATA = [
  { cohort: '2026-01', data: [100, 61, 48, 40, 34, 28] },
  { cohort: '2026-02', data: [100, 64, 52, 43, 36, null] },
  { cohort: '2026-03', data: [100, 66, 55, 46, null, null] },
  { cohort: '2026-04', data: [100, 68, 57, null, null, null] },
  { cohort: '2026-05', data: [100, 69, null, null, null, null] },
  { cohort: '2026-06', data: [100, null, null, null, null, null] },
];

function renderRevenueSection() {
  // KPI cards
  const kpiContainer = document.getElementById('revenue-kpi-cards');
  if (kpiContainer) {
    const mrr = REVENUE_MONTHLY[REVENUE_MONTHLY.length - 1];
    const arr = Math.round(mrr * 12);
    const prevMrr = REVENUE_MONTHLY[REVENUE_MONTHLY.length - 2];
    const mom = (((mrr - prevMrr) / prevMrr) * 100).toFixed(1);
    kpiContainer.innerHTML = `
      <div class="kpi-card">
        <div class="kpi-label">MRR (本月)</div>
        <div class="kpi-value">¥${mrr}</div>
        <div class="kpi-badge kpi-badge-up">▲ +${mom}% MoM</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">ARR 预测</div>
        <div class="kpi-value">¥${arr}</div>
        <div class="kpi-badge kpi-badge-gold">基于当月×12</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">MoM增长率</div>
        <div class="kpi-value">+${mom}%</div>
        <div class="kpi-badge kpi-badge-up">健康增长</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">付费用户数</div>
        <div class="kpi-value">128</div>
        <div class="kpi-badge kpi-badge-up">▲ +18</div>
      </div>`;
  }

  // MRR + paid users dual axis
  const ctxGmvUsers = document.getElementById('revGmvUsers');
  if (ctxGmvUsers) {
    createChart(ctxGmvUsers, {
      type: 'bar',
      data: {
        labels: MONTHS_12_LABEL,
        datasets: [
          { label: 'MRR (元)', data: REVENUE_MONTHLY, backgroundColor: 'rgba(200,169,110,0.7)', borderColor: GOLD, borderWidth: 1, borderRadius: 4, yAxisID: 'y' },
          { label: '付费用户数', data: USERS_MONTHLY, type: 'line', borderColor: BLUE, backgroundColor: 'rgba(52,152,219,0.08)', borderWidth: 2, pointRadius: 3, pointBackgroundColor: BLUE, fill: true, tension: 0.4, yAxisID: 'y1' }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { color: WHITE } }, tooltip: makeTooltipOptions() },
        scales: {
          x:  { grid: { display: false }, ticks: { color: GRAY } },
          y:  { position: 'left',  grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v } },
          y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { color: BLUE, callback: v => v } }
        }
      }
    });
  }

  // Tier stacked area
  const ctxTierStack = document.getElementById('revTierStack');
  if (ctxTierStack) {
    const tierColors = ['rgba(90,86,80,0.6)', 'rgba(52,152,219,0.7)', 'rgba(46,204,113,0.7)', 'rgba(200,169,110,0.8)'];
    const tierNames  = Object.keys(TIER_REVENUE);
    createChart(ctxTierStack, {
      type: 'line',
      data: {
        labels: MONTHS_12_LABEL,
        datasets: tierNames.map((tier, i) => ({
          label: tier,
          data: TIER_REVENUE[tier],
          backgroundColor: tierColors[i],
          borderColor: tierColors[i].replace(/[\d.]+\)$/, '1)'),
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 3,
        }))
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: WHITE, font: { size: 11 } } }, tooltip: makeTooltipOptions() },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: GRAY } },
          y: { stacked: true, grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v } }
        }
      }
    });
  }

  // Channel revenue bar
  const ctxRevChannel = document.getElementById('revChannelBar');
  if (ctxRevChannel) {
    createChart(ctxRevChannel, {
      type: 'bar',
      data: {
        labels: CHANNEL_DATA.map(c => c.name),
        datasets: [{
          label: '月度营收（元）',
          data: CHANNEL_DATA.map(c => c.revenue),
          backgroundColor: CHANNEL_COLORS.map(c => c + 'CC'),
          borderColor: CHANNEL_COLORS,
          borderWidth: 1,
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: makeTooltipOptions({ callbacks: { label: c => ` ¥${c.raw}` } }) },
        scales: {
          x: { grid: { display: false }, ticks: { color: GRAY } },
          y: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v } }
        }
      }
    });
  }

  // Cohort table
  const thead = document.getElementById('cohort-thead');
  const tbody = document.getElementById('cohort-tbody');
  if (thead && tbody) {
    thead.innerHTML = '<th>队列</th>' + ['M0','M1','M2','M3','M4','M5'].map(m => `<th>${m}</th>`).join('');
    tbody.innerHTML = COHORT_DATA.map(row => {
      const cells = row.data.map(v => {
        if (v === null) return `<td style="color:var(--gray-600)">—</td>`;
        const intensity = v / 100;
        const bg = `rgba(200,169,110,${(intensity * 0.5 + 0.05).toFixed(2)})`;
        const color = intensity > 0.6 ? NAVY : WHITE;
        return `<td style="background:${bg};color:${color};font-weight:600">${v}%</td>`;
      }).join('');
      return `<tr><td style="color:var(--gold);font-weight:500">${row.cohort}</td>${cells}</tr>`;
    }).join('');
  }
}


// ============================================================
//  SECTION 5: 用户分层  (Segment)
// ============================================================
const SEG_TIERS = [
  { name: '免费用户', count: 880, pct: 69.4, arpu: 0, ltv: 0, r7: '38%', r30: '16%', r90: '7%', color: '#4A5568' },
  { name: '验证版会员', count: 214, pct: 16.9, arpu: 68, ltv: 420, r7: '68%', r30: '48%', r90: '34%', color: '#3182CE' },
  { name: '专业会员', count: 128, pct: 10.1, arpu: 198, ltv: 1260, r7: '82%', r30: '70%', r90: '56%', color: '#38A169' },
  { name: '机构试点', count: 34, pct: 2.7, arpu: 1820, ltv: 12800, r7: '91%', r30: '84%', r90: '76%', color: '#C8A96E' },
];

const LIFECYCLE_STAGES = [
  { icon: '👀', name: '内容触达', desc: '种子内容与合作分发', num: '6.8万' },
  { icon: '🏠', name: '私域留资', desc: '社群 / 注册 / 演示预约', num: '5,400' },
  { icon: '💡', name: '激活试用', desc: '完成首次分析与复盘', num: '1,260' },
  { icon: '💳', name: '首次付费', desc: '购买验证版或专业版', num: '128' },
  { icon: '👑', name: '高频留存', desc: '复购 / 升级 / 持续使用', num: '36' },
];

function renderSegmentSection() {
  // HTML Funnel
  const funnelContainer = document.getElementById('seg-funnel-container');
  if (funnelContainer) {
    const tiers = [
      { label: '免费用户', count: 1268, color: '#4A5568', convFrom: null, convTo: '16.9%' },
      { label: '验证版会员', count: 214, color: '#3182CE', convFrom: '16.9%', convTo: '59.8%' },
      { label: '专业会员', count: 128, color: '#38A169', convFrom: '59.8%', convTo: '26.6%' },
      { label: '机构试点', count: 34, color: '#C8A96E', convFrom: '26.6%', convTo: null },
    ];
    const maxCount = tiers[0].count;
    funnelContainer.innerHTML = tiers.map((t, i) => {
      const w = Math.round((t.count / maxCount) * 80) + 20;
      return `<div style="margin:8px auto;width:${w}%;max-width:800px;background:${t.color}22;border:1px solid ${t.color}66;border-radius:6px;padding:12px 20px;display:flex;align-items:center;justify-content:space-between;transition:all 0.3s">
        <div style="font-weight:600;color:${t.color};font-size:14px">${t.label}</div>
        <div style="color:var(--white);font-size:16px;font-weight:700">${t.count.toLocaleString()}</div>
        <div style="color:var(--gray-400);font-size:12px">${t.convFrom ? '付费转化 '+t.convFrom : '总注册用户'}</div>
      </div>
      ${t.convTo ? '<div style="text-align:center;color:var(--gold);font-size:12px;margin:2px 0">↓ 转化率 '+t.convTo+'</div>' : ''}`;
    }).join('');
  }

  // Tier donut
  const ctxSegDonut = document.getElementById('segTierDonut');
  if (ctxSegDonut) {
    createChart(ctxSegDonut, {
      type: 'doughnut',
      data: {
        labels: SEG_TIERS.map(t => t.name),
        datasets: [{
          data: SEG_TIERS.map(t => t.count),
          backgroundColor: SEG_TIERS.map(t => t.color + 'CC'),
          borderColor: SEG_TIERS.map(t => t.color),
          borderWidth: 2,
          hoverOffset: 8,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '60%',
        plugins: { legend: { position: 'right', labels: { color: WHITE, font: { size: 12 }, padding: 14, boxWidth: 12 } } }
      }
    });
  }

  // ARPU bar
  const ctxArpu = document.getElementById('segArpuBar');
  if (ctxArpu) {
    createChart(ctxArpu, {
      type: 'bar',
      data: {
        labels: SEG_TIERS.filter(t => t.arpu > 0).map(t => t.name),
        datasets: [{
          label: 'ARPU (¥/月)',
          data: SEG_TIERS.filter(t => t.arpu > 0).map(t => t.arpu),
          backgroundColor: SEG_TIERS.filter(t => t.arpu > 0).map(t => t.color + 'CC'),
          borderColor: SEG_TIERS.filter(t => t.arpu > 0).map(t => t.color),
          borderWidth: 1,
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: makeTooltipOptions({ callbacks: { label: c => ` ARPU: ¥${c.raw}/月` } }) },
        scales: {
          x: { grid: { display: false }, ticks: { color: GRAY } },
          y: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v } }
        }
      }
    });
  }

  // Lifecycle flow HTML
  const flowContainer = document.getElementById('lifecycle-flow');
  if (flowContainer) {
    flowContainer.innerHTML = LIFECYCLE_STAGES.map((s, i) => `
      ${i > 0 ? '<div class="lifecycle-arrow">→</div>' : ''}
      <div class="lifecycle-stage">
        <div class="lifecycle-icon">${s.icon}</div>
        <div class="lifecycle-name">${s.name}</div>
        <div class="lifecycle-desc">${s.desc}</div>
        <div class="lifecycle-num">${s.num}</div>
      </div>`).join('');
  }

  // Retention table
  const retentionBody = document.getElementById('retention-body');
  if (retentionBody) {
    retentionBody.innerHTML = SEG_TIERS.map(t => {
      const r7Color  = parseInt(t.r7) > 70 ? '#2ECC71' : parseInt(t.r7) > 40 ? GOLD : '#E74C3C';
      const r30Color = parseInt(t.r30) > 60 ? '#2ECC71' : parseInt(t.r30) > 30 ? GOLD : '#E74C3C';
      const r90Color = parseInt(t.r90) > 50 ? '#2ECC71' : parseInt(t.r90) > 20 ? GOLD : '#E74C3C';
      return `<tr>
        <td style="color:${t.color};font-weight:600">${t.name}</td>
        <td>${t.count.toLocaleString()}</td>
        <td style="color:${r7Color};font-weight:600">${t.r7}</td>
        <td style="color:${r30Color};font-weight:600">${t.r30}</td>
        <td style="color:${r90Color};font-weight:600">${t.r90}</td>
        <td style="color:var(--gold)">${t.arpu > 0 ? '¥' + t.arpu : '—'}</td>
        <td style="color:var(--gold)">${t.ltv > 0 ? '¥' + t.ltv.toLocaleString() : '—'}</td>
      </tr>`;
    }).join('');
  }
}


// ============================================================
//  INIT: render funnel section on load (default section)
// ============================================================
window.initDashboardCharts = initDashboardCharts;
window.showDashSection = showDashSection;

document.addEventListener('gangtise:themechange', () => {
  const active = getActiveDashSection();
  if (active) {
    rerenderDashboardSection(active);
  } else {
    updateChartDefaults();
  }
});

document.addEventListener('DOMContentLoaded', () => {
  updateChartDefaults();
  if (window.AUTO_INIT_DASHBOARD === false) return;
  if (document.getElementById('ds-funnel')) {
    initDashboardCharts(window.dashboardDefaultSection || 'funnel');
  }
});
