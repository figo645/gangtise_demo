// ============================================================
//  Gangtise Dashboard Charts  –  charts.js
//  Supports 5 sections: funnel | channel | kol | revenue | segment
//  Lazy rendering: each section renders once on first visit
// ============================================================

// ---- Brand palette ----
const GOLD        = '#C8A96E';
const GOLD_LIGHT  = '#E2C98A';
const GOLD_DARK   = '#A8893E';
const NAVY        = '#0D1B2A';
const NAVY_MID    = '#1A2E45';
const WHITE       = '#F8F6F0';
const GRAY        = '#9A9590';
const GREEN       = '#2ECC71';
const RED         = '#E74C3C';
const BLUE        = '#3498DB';

const CHANNEL_COLORS  = ['#07C160', '#FE2C55', '#FF2442', '#E6162D', '#C8A96E'];
const SEGMENT_COLORS  = ['#4A5568', '#3182CE', '#38A169', '#C8A96E', '#FFD700'];
const TIER_COLORS     = ['#4A5568', '#3182CE', '#38A169', '#C8A96E'];

// Chart.js defaults
Chart.defaults.color           = GRAY;
Chart.defaults.borderColor     = 'rgba(200,169,110,0.08)';
Chart.defaults.font.family     = "'PingFang SC', 'Microsoft YaHei', sans-serif";

// Track which sections have been rendered
const renderedSections = new Set();

// ============================================================
//  SECTION NAVIGATION
// ============================================================
const SECTION_TITLES = {
  funnel:  '多渠道多圈层转化分析',
  channel: '渠道分析',
  kol:     'KOL效能分析',
  revenue: '营收趋势',
  segment: '用户分层分析',
};

function showDashSection(section) {
  // Update nav active state
  document.querySelectorAll('.admin-nav-item').forEach(el => el.classList.remove('active'));
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
  return Object.assign({ backgroundColor: NAVY_MID, borderColor: GOLD, borderWidth: 1 }, extra || {});
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
  container.innerHTML = data.map((item, i) => {
    const widthPct  = Math.round((item.count / maxCount) * 100);
    const dropRate  = i > 0 ? ((data[i-1].count - item.count) / data[i-1].count * 100).toFixed(1) : null;
    return `
      <div class="funnel-row">
        <div class="funnel-label">${item.layer}</div>
        <div class="funnel-bar-wrap">
          <div class="funnel-bar" style="width:${widthPct}%">${widthPct > 20 ? item.layer : ''}</div>
        </div>
        <div class="funnel-count">${(item.count/10000).toFixed(1)}万</div>
        <div class="funnel-rate">${dropRate ? '↓'+dropRate+'%' : '基准'}</div>
      </div>`;
  }).join('');
}

// --- Channel donut ---
async function renderChannelDonut() {
  const res  = await fetch('/api/channels');
  const data = await res.json();
  const ctx  = document.getElementById('channelDonut');
  if (!ctx) return;
  new Chart(ctx, {
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
        legend: { position: 'right', labels: { color: WHITE, font: { size: 12 }, padding: 12, boxWidth: 12 } },
        tooltip: { callbacks: { label: c => ` ${c.label}: ${(c.raw/10000).toFixed(1)}万用户` } }
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
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.month.slice(5)),
      datasets: [
        {
          label: 'GMV (万元)',
          data: data.map(d => Math.round(d.revenue / 10000)),
          backgroundColor: 'rgba(200,169,110,0.7)',
          borderColor: GOLD, borderWidth: 1, borderRadius: 4, yAxisID: 'y',
        },
        {
          label: '新增用户',
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
        y:  { position: 'left',  grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v+'万' } },
        y1: { position: 'right', grid: { drawOnChartArea: false },           ticks: { color: BLUE,  callback: v => v/1000+'K' } }
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
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.name),
      datasets: [
        {
          label: 'GMV (元)',
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
        tooltip: makeTooltipOptions({ callbacks: { label: c => ` ${c.dataset.label}: ¥${(c.raw/10000).toFixed(1)}万` } })
      },
      scales: {
        x: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+(v/10000).toFixed(0)+'万' } },
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
  new Chart(ctx, {
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
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.name),
      datasets: [{ label: '月度营收 (万元)', data: data.map(d => Math.round(d.revenue/10000)), backgroundColor: CHANNEL_COLORS.map(c => c+'CC'), borderColor: CHANNEL_COLORS, borderWidth: 1, borderRadius: 6 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: makeTooltipOptions({ callbacks: { label: c => ` ¥${c.raw}万` } }) },
      scales: {
        x: { grid: { display: false }, ticks: { color: GRAY } },
        y: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v+'万' } }
      }
    }
  });
}

// --- Heatmap table ---
async function renderHeatmap() {
  const channels = ['微信生态', '抖音', '小红书', '微博', '直接流量'];
  const matrix   = [
    [100, 28.4, 7.2, 2.1, 0.48],
    [100, 18.6, 4.8, 1.4, 0.32],
    [100, 32.1, 9.4, 3.9, 0.92],
    [100, 15.2, 3.8, 0.8, 0.18],
    [100, 42.8, 14.6, 9.9, 2.24],
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
  { name: '微信生态', users: 98400,  convRate: '2.8%', revenue: 2840000, cac: 42,  ltv: 680, score: 88, trend: '▲', trendCls: 'trend-up' },
  { name: '抖音',     users: 64200,  convRate: '1.4%', revenue: 1560000, cac: 68,  ltv: 420, score: 72, trend: '▲', trendCls: 'trend-up' },
  { name: '小红书',   users: 42800,  convRate: '3.9%', revenue: 1920000, cac: 55,  ltv: 590, score: 81, trend: '▲', trendCls: 'trend-up' },
  { name: '微博',     users: 28600,  convRate: '0.8%', revenue: 680000,  cac: 88,  ltv: 310, score: 54, trend: '▼', trendCls: 'trend-down' },
  { name: '直接流量', users: 17200,  convRate: '9.9%', revenue: 1960000, cac: 18,  ltv: 1240, score: 95, trend: '▲', trendCls: 'trend-up' },
];

const MONTHS_12 = ['2024-01','2024-02','2024-03','2024-04','2024-05','2024-06','2024-07','2024-08','2024-09','2024-10','2024-11','2024-12'];
const MONTHS_12_LABEL = MONTHS_12.map(m => m.slice(5)+'月');

// Monthly channel acquisition (stacked bar data, in thousands)
const CHANNEL_MONTHLY = [
  [5.2, 5.4, 5.8, 6.1, 6.4, 6.8, 7.1, 7.4, 7.8, 8.1, 8.4, 8.6],  // 微信
  [2.8, 3.1, 3.5, 3.8, 4.2, 4.6, 5.0, 5.4, 5.8, 6.1, 6.4, 6.6],  // 抖音
  [1.6, 1.8, 2.1, 2.4, 2.7, 3.0, 3.3, 3.6, 3.9, 4.1, 4.3, 4.6],  // 小红书
  [1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3],  // 微博
  [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9],  // 直接
];

function renderChannelSection() {
  // KPI cards
  const kpiContainer = document.getElementById('channel-kpi-cards');
  if (kpiContainer) {
    kpiContainer.innerHTML = CHANNEL_DATA.map(ch => `
      <div class="kpi-card">
        <div class="kpi-label">${ch.name}</div>
        <div class="kpi-value" style="font-size:20px">${(ch.users/10000).toFixed(1)}万</div>
        <div class="kpi-sub">转化率 ${ch.convRate}</div>
        <div class="kpi-sub">营收 ${(ch.revenue/10000).toFixed(0)}万</div>
        <div class="kpi-badge ${ch.trendCls === 'trend-up' ? 'kpi-badge-up' : 'kpi-badge-down'}">
          CAC ¥${ch.cac} · LTV ¥${ch.ltv}
        </div>
      </div>`).join('');
  }

  // Stacked bar – channel monthly acquisition
  const ctxStack = document.getElementById('channelStackedBar');
  if (ctxStack) {
    new Chart(ctxStack, {
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
          y: { stacked: true, grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => v+'K' } }
        }
      }
    });
  }

  // Scatter / Bubble – CAC vs LTV
  const ctxScatter = document.getElementById('cacLtvScatter');
  if (ctxScatter) {
    new Chart(ctxScatter, {
      type: 'bubble',
      data: {
        datasets: CHANNEL_DATA.map((ch, i) => ({
          label: ch.name,
          data: [{ x: ch.cac, y: ch.ltv, r: Math.sqrt(ch.users / 1000) * 2.5 }],
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
        <td>${(ch.users/10000).toFixed(1)}万</td>
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
//  SECTION 3: KOL效能  (KOL)
// ============================================================
const KOL_TOP10 = [
  { name: '财经老王', platform: '抖音',     fans: '128万', gmv: 980000,  commission: 196000, rate: '20%', tier: 'S', trend: '+24%' },
  { name: '投研精选',  platform: '微信',     fans: '86万',  gmv: 820000,  commission: 164000, rate: '20%', tier: 'S', trend: '+18%' },
  { name: '量化阿杰',  platform: '小红书',   fans: '54万',  gmv: 640000,  commission: 112000, rate: '18%', tier: 'A', trend: '+12%' },
  { name: '宏观视野',  platform: '抖音',     fans: '92万',  gmv: 580000,  commission: 104400, rate: '18%', tier: 'A', trend: '+8%' },
  { name: '策略研究员', platform: '微信',     fans: '38万',  gmv: 450000,  commission: 72000,  rate: '16%', tier: 'A', trend: '+6%' },
  { name: '行业深度',  platform: '微博',     fans: '62万',  gmv: 380000,  commission: 60800,  rate: '16%', tier: 'A', trend: '-2%' },
  { name: '晨会纪要',  platform: '小红书',   fans: '29万',  gmv: 290000,  commission: 43500,  rate: '15%', tier: 'B', trend: '+14%' },
  { name: '大盘解读',  platform: '抖音',     fans: '41万',  gmv: 260000,  commission: 39000,  rate: '15%', tier: 'B', trend: '+3%' },
  { name: '板块追踪',  platform: '微信',     fans: '18万',  gmv: 210000,  commission: 31500,  rate: '15%', tier: 'B', trend: '-5%' },
  { name: '新能源专研', platform: '小红书',  fans: '23万',  gmv: 180000,  commission: 27000,  rate: '15%', tier: 'B', trend: '+9%' },
];

const KOL_TIER_GROWTH = {
  S: [2, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 9],
  A: [12, 13, 15, 16, 18, 20, 22, 25, 28, 31, 35, 38],
  B: [45, 48, 52, 56, 62, 68, 74, 82, 90, 98, 108, 118],
};

function renderKolSection() {
  // KPI cards
  const kpiContainer = document.getElementById('kol-kpi-cards');
  if (kpiContainer) {
    const totalGmv = KOL_TOP10.reduce((s, k) => s + k.gmv, 0);
    const totalKols = 165;
    const avgRate = '17.2%';
    const topKol = KOL_TOP10[0].name;
    kpiContainer.innerHTML = `
      <div class="kpi-card">
        <div class="kpi-label">总KOL合伙人</div>
        <div class="kpi-value">${totalKols}</div>
        <div class="kpi-badge kpi-badge-up">▲ +14 本月</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">合伙人总GMV</div>
        <div class="kpi-value">¥${(totalGmv/10000).toFixed(0)}万</div>
        <div class="kpi-badge kpi-badge-up">▲ +22%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">平均佣金率</div>
        <div class="kpi-value">${avgRate}</div>
        <div class="kpi-badge kpi-badge-gold">加权平均</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">月度最佳 KOL</div>
        <div class="kpi-value" style="font-size:18px">${topKol}</div>
        <div class="kpi-badge kpi-badge-gold">S级合伙人</div>
      </div>`;
  }

  // Top 10 horizontal bar
  const ctxTop10 = document.getElementById('kolTop10Bar');
  if (ctxTop10) {
    new Chart(ctxTop10, {
      type: 'bar',
      data: {
        labels: KOL_TOP10.map(k => k.name),
        datasets: [
          {
            label: 'GMV (万元)',
            data: KOL_TOP10.map(k => (k.gmv / 10000).toFixed(1)),
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
          tooltip: makeTooltipOptions({ callbacks: { label: c => ` GMV: ¥${c.raw}万` } })
        },
        scales: {
          x: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v+'万' } },
          y: { grid: { display: false }, ticks: { color: WHITE, font: { size: 11 } } }
        }
      }
    });
  }

  // Tier growth line chart
  const ctxTierGrowth = document.getElementById('kolTierGrowth');
  if (ctxTierGrowth) {
    new Chart(ctxTierGrowth, {
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
    new Chart(ctxTierDonut, {
      type: 'doughnut',
      data: {
        labels: ['S级', 'A级', 'B级'],
        datasets: [{
          data: [9, 38, 118],
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
        <td style="color:var(--gold);font-weight:600">¥${(k.gmv/10000).toFixed(1)}万</td>
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
const REVENUE_MONTHLY = [42, 48, 54, 58, 63, 68, 72, 78, 82, 88, 94, 102]; // 万元
const USERS_MONTHLY   = [8200, 9400, 10800, 11600, 12800, 13900, 14800, 16200, 17400, 18600, 19800, 21200];

const TIER_REVENUE = {
  '免费':   [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  '基础会员': [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20],
  '专业会员': [18, 21, 24, 26, 28, 30, 32, 34, 36, 38, 41, 44],
  'VIP机构':  [16, 18, 20, 21, 23, 25, 26, 29, 30, 33, 35, 38],
};

const COHORT_DATA = [
  { cohort: '2024-07', data: [100, 72, 58, 48, 41, 36] },
  { cohort: '2024-08', data: [100, 74, 61, 51, 44, null] },
  { cohort: '2024-09', data: [100, 76, 63, 53, null, null] },
  { cohort: '2024-10', data: [100, 78, 65, null, null, null] },
  { cohort: '2024-11', data: [100, 80, null, null, null, null] },
  { cohort: '2024-12', data: [100, null, null, null, null, null] },
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
        <div class="kpi-value">¥${mrr}万</div>
        <div class="kpi-badge kpi-badge-up">▲ +${mom}% MoM</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">ARR 预测</div>
        <div class="kpi-value">¥${arr}万</div>
        <div class="kpi-badge kpi-badge-gold">基于当月×12</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">MoM增长率</div>
        <div class="kpi-value">+${mom}%</div>
        <div class="kpi-badge kpi-badge-up">健康增长</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">付费用户数</div>
        <div class="kpi-value">21,200</div>
        <div class="kpi-badge kpi-badge-up">▲ +1,400</div>
      </div>`;
  }

  // GMV + Users dual axis
  const ctxGmvUsers = document.getElementById('revGmvUsers');
  if (ctxGmvUsers) {
    new Chart(ctxGmvUsers, {
      type: 'bar',
      data: {
        labels: MONTHS_12_LABEL,
        datasets: [
          { label: 'GMV (万元)', data: REVENUE_MONTHLY, backgroundColor: 'rgba(200,169,110,0.7)', borderColor: GOLD, borderWidth: 1, borderRadius: 4, yAxisID: 'y' },
          { label: '付费用户数', data: USERS_MONTHLY, type: 'line', borderColor: BLUE, backgroundColor: 'rgba(52,152,219,0.08)', borderWidth: 2, pointRadius: 3, pointBackgroundColor: BLUE, fill: true, tension: 0.4, yAxisID: 'y1' }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { color: WHITE } }, tooltip: makeTooltipOptions() },
        scales: {
          x:  { grid: { display: false }, ticks: { color: GRAY } },
          y:  { position: 'left',  grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v+'万' } },
          y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { color: BLUE, callback: v => (v/1000).toFixed(0)+'K' } }
        }
      }
    });
  }

  // Tier stacked area
  const ctxTierStack = document.getElementById('revTierStack');
  if (ctxTierStack) {
    const tierColors = ['rgba(90,86,80,0.6)', 'rgba(52,152,219,0.7)', 'rgba(46,204,113,0.7)', 'rgba(200,169,110,0.8)'];
    const tierNames  = Object.keys(TIER_REVENUE);
    new Chart(ctxTierStack, {
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
          y: { stacked: true, grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v+'万' } }
        }
      }
    });
  }

  // Channel revenue bar
  const ctxRevChannel = document.getElementById('revChannelBar');
  if (ctxRevChannel) {
    new Chart(ctxRevChannel, {
      type: 'bar',
      data: {
        labels: CHANNEL_DATA.map(c => c.name),
        datasets: [{
          label: '月度营收（万元）',
          data: CHANNEL_DATA.map(c => Math.round(c.revenue / 10000)),
          backgroundColor: CHANNEL_COLORS.map(c => c + 'CC'),
          borderColor: CHANNEL_COLORS,
          borderWidth: 1,
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: makeTooltipOptions({ callbacks: { label: c => ` ¥${c.raw}万` } }) },
        scales: {
          x: { grid: { display: false }, ticks: { color: GRAY } },
          y: { grid: { color: 'rgba(200,169,110,0.06)' }, ticks: { color: GRAY, callback: v => '¥'+v+'万' } }
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
  { name: '免费用户',  count: 229800, pct: 91.5, arpu: 0,    ltv: 0,    r7: '42%', r30: '18%', r90: '8%',  color: '#4A5568' },
  { name: '基础会员',  count: 12400,  pct: 4.9,  arpu: 68,   ltv: 480,  r7: '72%', r30: '54%', r90: '38%', color: '#3182CE' },
  { name: '专业会员',  count: 5200,   pct: 2.1,  arpu: 198,  ltv: 1420, r7: '86%', r30: '74%', r90: '62%', color: '#38A169' },
  { name: 'VIP机构',   count: 3600,   pct: 1.4,  arpu: 1820, ltv: 18200,r7: '94%', r30: '88%', r90: '80%', color: '#C8A96E' },
];

const LIFECYCLE_STAGES = [
  { icon: '👀', name: '公域曝光',  desc: '微信/抖音等多渠道触达', num: '980万' },
  { icon: '🏠', name: '私域沉淀',  desc: '关注公众号/加入社群',   num: '24.5万' },
  { icon: '💡', name: '主动意向',  desc: '点击注册/浏览产品',     num: '9.8万' },
  { icon: '💳', name: '首次付费',  desc: '购买基础或专业套餐',    num: '1.85万' },
  { icon: '👑', name: 'VIP升级',   desc: '升级机构VIP订阅',      num: '4,200' },
];

function renderSegmentSection() {
  // HTML Funnel
  const funnelContainer = document.getElementById('seg-funnel-container');
  if (funnelContainer) {
    const tiers = [
      { label: '免费用户',   count: 251000, color: '#4A5568', convFrom: null,     convTo: '4.9%' },
      { label: '基础会员',   count: 12400,  color: '#3182CE', convFrom: '4.9%',  convTo: '42%' },
      { label: '专业会员',   count: 5200,   color: '#38A169', convFrom: '42%',   convTo: '69%' },
      { label: 'VIP机构',    count: 3600,   color: '#C8A96E', convFrom: '69%',   convTo: null },
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
    new Chart(ctxSegDonut, {
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
    new Chart(ctxArpu, {
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
document.addEventListener('DOMContentLoaded', () => {
  renderedSections.add('funnel');
  renderFunnelSection();
});
