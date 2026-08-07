// ============================================================
//  Gangtise Dashboard Charts – ECharts Edition
//  Supports: funnel | channel | kol | revenue | segment
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
    textMain: themeVar('--text-main', '#182132'),
    textSub: themeVar('--text-sub', '#5A6572'),
    gray: themeVar('--gray-400', '#9A9590'),
    green: '#2ECC71',
    red: '#E74C3C',
    blue: '#2F74C0',
    blueSoft: 'rgba(47,116,192,0.16)',
  };
}

const CHANNEL_COLORS = ['#07C160', '#FE2C55', '#FF2442', '#E6162D', '#C8A96E'];
const SEGMENT_COLORS = ['#4A5568', '#3182CE', '#38A169', '#C8A96E', '#FFD700'];

const renderedSections = new Set();
const chartRegistry = new Set();

function registerChartTarget(target) {
  const key = typeof target === 'string' ? target : (target && target.id) || '';
  if (key) chartRegistry.add(key);
}

function destroyRegisteredCharts() {
  if (!window.GangtiseEcharts) return;
  chartRegistry.forEach((key) => window.GangtiseEcharts.dispose(key));
  chartRegistry.clear();
}

function renderChart(target, option) {
  if (!window.GangtiseEcharts) return null;
  registerChartTarget(target);
  return window.GangtiseEcharts.render(target, option || {});
}

function baseLegend(overrides) {
  return window.GangtiseEcharts.legendBase(Object.assign({
    textStyle: { color: currentPalette().textSub, fontSize: 11 },
  }, overrides || {}));
}

function baseGrid(overrides) {
  return window.GangtiseEcharts.gridBase(overrides || {});
}

function baseAxis(overrides) {
  return window.GangtiseEcharts.axisBase(Object.assign({
    axisLabel: { color: currentPalette().textSub, fontSize: 11 },
    splitLine: { lineStyle: { color: window.GangtiseEcharts.rgba(currentPalette().blue, 0.08) } },
  }, overrides || {}));
}

function baseTooltip(formatter) {
  return window.GangtiseEcharts.tooltipBase(formatter);
}

function timeZoom(labels) {
  if (!Array.isArray(labels) || labels.length < 7) return [];
  const palette = currentPalette();
  return [
    { type: 'inside', xAxisIndex: [0] },
    {
      type: 'slider',
      xAxisIndex: [0],
      height: 18,
      bottom: 12,
      borderColor: 'transparent',
      backgroundColor: window.GangtiseEcharts.rgba(palette.blue, 0.05),
      fillerColor: window.GangtiseEcharts.rgba(palette.blue, 0.14),
      handleSize: 0,
    },
  ];
}

function showDashSection(section) {
  document.querySelectorAll('[id^="nav-"]').forEach((el) => el.classList.remove('active'));
  const navEl = document.getElementById('nav-' + section);
  if (navEl) navEl.classList.add('active');

  document.querySelectorAll('.dash-section').forEach((el) => el.classList.remove('active'));
  const secEl = document.getElementById('ds-' + section);
  if (secEl) secEl.classList.add('active');

  const titleEl = document.getElementById('topbar-title');
  if (titleEl) titleEl.textContent = SECTION_TITLES[section] || '';

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
  destroyRegisteredCharts();
  renderedSections.clear();
  if (document.getElementById('ds-' + section)) showDashSection(section);
}

function initDashboardCharts(initialSection) {
  const section = initialSection || getActiveDashSection() || 'funnel';
  rerenderDashboardSection(section);
}

function renderSection(section) {
  switch (section) {
    case 'funnel':
      renderFunnelSection();
      break;
    case 'channel':
      renderChannelSection();
      break;
    case 'kol':
      renderKolSection();
      break;
    case 'revenue':
      renderRevenueSection();
      break;
    case 'segment':
      renderSegmentSection();
      break;
    default:
      break;
  }
}

function setDateRange(btn) {
  document.querySelectorAll('.date-btn').forEach((item) => item.classList.remove('active'));
  if (btn) btn.classList.add('active');
}

function makeDonutOption(labels, values, colors, extra) {
  const palette = currentPalette();
  return {
    color: colors,
    tooltip: baseTooltip((params) => `${params.name}<br>数量：${params.value}`),
    legend: baseLegend({ orient: 'vertical', right: 0, top: 'middle' }),
    series: [
      {
        type: 'pie',
        radius: ['52%', '74%'],
        center: extra && extra.center ? extra.center : ['40%', '50%'],
        itemStyle: {
          borderColor: '#FFFFFF',
          borderWidth: 2,
          borderRadius: 8,
        },
        label: { show: false },
        emphasis: {
          scale: true,
          itemStyle: {
            shadowBlur: 18,
            shadowColor: window.GangtiseEcharts.rgba(palette.blue, 0.20),
          },
        },
        data: labels.map((label, index) => ({ name: label, value: values[index] || 0 })),
      },
    ],
  };
}

function makeVerticalBarOption(labels, datasets, extra) {
  const palette = currentPalette();
  const rows = Array.isArray(datasets) ? datasets : [];
  return {
    color: rows.map((item) => item.color),
    tooltip: baseTooltip((params) => {
      const list = Array.isArray(params) ? params : [params];
      return [`<div style="font-weight:700;margin-bottom:6px">${list[0].axisValueLabel}</div>`]
        .concat(list.map((item) => `${item.marker}${item.seriesName}：${item.value}`))
        .join('<br>');
    }),
    legend: baseLegend({ top: 0 }),
    grid: baseGrid({ top: 36, left: 14, right: extra && extra.rightAxis ? 36 : 18, bottom: 54 }),
    dataZoom: extra && extra.zoom ? timeZoom(labels) : [],
    xAxis: {
      type: 'category',
      data: labels,
      ...baseAxis({ splitLine: { show: false } }),
    },
    yAxis: extra && extra.rightAxis ? [
      {
        type: 'value',
        ...baseAxis({ axisLabel: { color: palette.textSub, fontSize: 11, formatter: extra.leftFormatter || '{value}' } }),
      },
      {
        type: 'value',
        position: 'right',
        ...baseAxis({
          splitLine: { show: false },
          axisLabel: { color: palette.blue, fontSize: 11, formatter: extra.rightFormatter || '{value}' },
        }),
      },
    ] : {
      type: 'value',
      ...baseAxis({ axisLabel: { color: palette.textSub, fontSize: 11, formatter: extra && extra.leftFormatter ? extra.leftFormatter : '{value}' } }),
    },
    series: rows.map((item) => ({
      name: item.name,
      type: item.type || 'bar',
      data: item.data,
      yAxisIndex: item.yAxisIndex || 0,
      stack: item.stack || '',
      smooth: item.type === 'line',
      symbol: item.type === 'line' ? 'circle' : 'none',
      symbolSize: item.type === 'line' ? 7 : 0,
      barWidth: item.type === 'bar' ? (item.barWidth || '42%') : undefined,
      lineStyle: item.type === 'line' ? { width: 2.5, color: item.color } : undefined,
      areaStyle: item.type === 'line' && item.area !== false ? { color: window.GangtiseEcharts.rgba(item.color, 0.10) } : undefined,
      itemStyle: item.type === 'bar' ? {
        color: item.color,
        borderRadius: item.borderRadius || [8, 8, 0, 0],
      } : { color: item.color },
    })),
  };
}

function makeHorizontalBarOption(labels, datasets, extra) {
  return {
    color: datasets.map((item) => item.color),
    tooltip: baseTooltip((params) => {
      const list = Array.isArray(params) ? params : [params];
      return [`<div style="font-weight:700;margin-bottom:6px">${list[0].axisValueLabel}</div>`]
        .concat(list.map((item) => `${item.marker}${item.seriesName}：${item.value}`))
        .join('<br>');
    }),
    legend: baseLegend({ top: 0 }),
    grid: baseGrid({ top: 36, left: 18, right: 18, bottom: 18 }),
    xAxis: {
      type: 'value',
      ...baseAxis({ axisLabel: { color: currentPalette().textSub, fontSize: 11, formatter: extra && extra.valueFormatter ? extra.valueFormatter : '{value}' } }),
    },
    yAxis: {
      type: 'category',
      data: labels,
      ...baseAxis({ splitLine: { show: false } }),
    },
    series: datasets.map((item) => ({
      name: item.name,
      type: 'bar',
      data: item.data,
      barWidth: item.barWidth || '40%',
      itemStyle: {
        color: item.color,
        borderRadius: [0, 10, 10, 0],
      },
    })),
  };
}

function makeBubbleOption(items) {
  const palette = currentPalette();
  return {
    tooltip: baseTooltip((params) => {
      const data = params.data || {};
      return [
        `<div style="font-weight:700;margin-bottom:6px">${params.seriesName}</div>`,
        `CAC：¥${data.value[0]}`,
        `LTV：¥${data.value[1]}`,
        `留资用户：${data.meta && data.meta.users ? data.meta.users : '--'}`,
      ].join('<br>');
    }),
    legend: baseLegend({ top: 0 }),
    grid: baseGrid({ top: 36, left: 18, right: 18, bottom: 24 }),
    xAxis: {
      type: 'value',
      name: 'CAC (¥)',
      nameTextStyle: { color: palette.textSub },
      ...baseAxis(),
    },
    yAxis: {
      type: 'value',
      name: 'LTV (¥)',
      nameTextStyle: { color: palette.textSub },
      ...baseAxis(),
    },
    series: items.map((item) => ({
      name: item.name,
      type: 'scatter',
      symbolSize: Math.max(Math.sqrt(item.users / 18), 10),
      data: [{ value: [item.cac, item.ltv], meta: item }],
      itemStyle: {
        color: window.GangtiseEcharts.rgba(item.color, 0.62),
        borderColor: item.color,
        borderWidth: 2,
      },
    })),
  };
}

function makeStackedAreaOption(labels, tiers) {
  return {
    color: tiers.map((item) => item.color),
    tooltip: baseTooltip((params) => {
      const list = Array.isArray(params) ? params : [params];
      return [`<div style="font-weight:700;margin-bottom:6px">${list[0].axisValueLabel}</div>`]
        .concat(list.map((item) => `${item.marker}${item.seriesName}：¥${item.value}`))
        .join('<br>');
    }),
    legend: baseLegend({ top: 0 }),
    grid: baseGrid({ top: 36, left: 18, right: 18, bottom: 54 }),
    dataZoom: timeZoom(labels),
    xAxis: {
      type: 'category',
      data: labels,
      ...baseAxis({ splitLine: { show: false } }),
    },
    yAxis: {
      type: 'value',
      ...baseAxis({ axisLabel: { color: currentPalette().textSub, fontSize: 11, formatter: '¥{value}' } }),
    },
    series: tiers.map((item) => ({
      name: item.name,
      type: 'line',
      smooth: true,
      stack: 'total',
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 2.2, color: item.color },
      areaStyle: { color: window.GangtiseEcharts.rgba(item.color, 0.16) },
      itemStyle: { color: item.color },
      data: item.data,
    })),
  };
}

const SECTION_TITLES = {
  funnel: '多渠道多圈层转化分析',
  channel: '渠道分析',
  kol: '作者协同效能分析',
  revenue: '营收趋势',
  segment: '用户分层分析',
};

function fmtWan(n) { return (n / 10000).toFixed(1) + '万'; }

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

async function renderFunnel() {
  const res = await fetch('/api/funnel');
  const data = await res.json();
  const container = document.getElementById('funnel-container');
  if (!container) return;
  const maxCount = data[0].count;
  const minWidthPct = 32;
  container.innerHTML = data.map((item, index) => {
    const widthPct = Math.round((item.count / maxCount) * 100);
    const dropRate = index > 0 ? ((data[index - 1].count - item.count) / data[index - 1].count * 100).toFixed(1) : null;
    const stageWidth = Math.max(widthPct, minWidthPct);
    return `
      <div class="funnel-stage-group">
        <div class="funnel-stage" style="width:${stageWidth}%">
          <div class="funnel-stage-box">
            <div class="funnel-stage-title">${item.layer}</div>
            <div class="funnel-stage-stats">
              <span class="funnel-stage-count">${fmtWan(item.count)}</span>
              <span class="funnel-stage-share">${item.rate.toFixed(1)}%</span>
            </div>
          </div>
        </div>
        <div class="funnel-stage-conv ${dropRate ? '' : 'funnel-stage-conv-base'}">${dropRate ? '↓ 较上一层流失 ' + dropRate + '%' : '验证起点'}</div>
      </div>`;
  }).join('');
}

async function renderChannelDonut() {
  const res = await fetch('/api/channels');
  const data = await res.json();
  const target = document.getElementById('channelDonut');
  if (!target) return;
  renderChart(target, makeDonutOption(
    data.map((item) => item.name),
    data.map((item) => item.users),
    CHANNEL_COLORS,
    { center: ['38%', '50%'] },
  ));
}

async function renderRevenueTrend() {
  const res = await fetch('/api/revenue');
  const data = await res.json();
  const target = document.getElementById('revenueTrend');
  if (!target) return;
  const labels = data.map((item) => item.month.slice(5));
  renderChart(target, makeVerticalBarOption(labels, [
    { name: 'MRR (元)', type: 'bar', data: data.map((item) => item.revenue), color: window.GangtiseEcharts.rgba(currentPalette().gold, 0.82), yAxisIndex: 0 },
    { name: '激活试用用户', type: 'line', data: data.map((item) => item.users), color: currentPalette().blue, yAxisIndex: 1 },
  ], {
    zoom: true,
    rightAxis: true,
    leftFormatter: '¥{value}',
    rightFormatter: '{value}',
  }));
}

async function renderKolBar() {
  const res = await fetch('/api/kols');
  const data = await res.json();
  const target = document.getElementById('kolBar');
  if (!target) return;
  renderChart(target, makeHorizontalBarOption(
    data.map((item) => item.name),
    [
      {
        name: '协同收入 (元)',
        data: data.map((item, index) => item.gmv),
        color: currentPalette().gold,
      },
      {
        name: '佣金 (元)',
        data: data.map((item) => item.commission),
        color: currentPalette().blue,
      },
    ],
    { valueFormatter: '¥{value}' },
  ));
}

async function renderSegmentDonut() {
  const res = await fetch('/api/segments');
  const data = await res.json();
  const target = document.getElementById('segmentDonut');
  if (!target) return;
  renderChart(target, makeDonutOption(
    data.map((item) => item.segment),
    data.map((item) => item.count),
    SEGMENT_COLORS,
    { center: ['50%', '50%'] },
  ));
  const legend = document.getElementById('segment-legend');
  if (legend) {
    legend.innerHTML = data.map((item, index) => `
      <div class="segment-item">
        <div class="segment-dot" style="background:${SEGMENT_COLORS[index]}"></div>
        <div class="segment-name">${item.segment}</div>
        <div class="segment-pct">${item.pct}%</div>
      </div>`).join('');
  }
}

async function renderChannelRevenue() {
  const res = await fetch('/api/channels');
  const data = await res.json();
  const target = document.getElementById('channelRevenue');
  if (!target) return;
  const labels = data.map((item) => item.name);
  renderChart(target, makeVerticalBarOption(labels, [
    { name: '月度营收 (元)', type: 'bar', data: data.map((item) => item.revenue), color: currentPalette().blue, yAxisIndex: 0 },
  ], {
    leftFormatter: '¥{value}',
  }));
}

async function renderHeatmap() {
  const channels = ['微信社群', '内容合作', '小红书', '转介绍', '直接流量'];
  const matrix = [
    [100, 12.0, 3.2, 0.9, 0.3],
    [100, 10.4, 2.7, 1.0, 0.28],
    [100, 8.1, 2.1, 0.7, 0.19],
    [100, 16.5, 4.4, 1.6, 0.52],
    [100, 18.0, 5.1, 2.4, 0.9],
  ];
  const tbody = document.getElementById('heatmap-body');
  if (!tbody) return;
  tbody.innerHTML = channels.map((channel, rowIndex) => `
    <tr>
      <td style="color:var(--text-main);font-weight:600">${channel}</td>
      ${matrix[rowIndex].map((value, cellIndex) => {
        const intensity = cellIndex === 0 ? 0.08 : Math.min(value / (cellIndex === 1 ? 45 : cellIndex === 2 ? 15 : cellIndex === 3 ? 10 : 2.5), 1);
        const bg = `rgba(200,169,110,${(intensity * 0.6 + 0.05).toFixed(2)})`;
        const color = intensity > 0.5 ? '#0D1B2A' : '#F8F6F0';
        return `<td style="background:${bg};color:${color};font-weight:${intensity > 0.4 ? '600' : '400'};text-align:center">${value}%</td>`;
      }).join('')}
    </tr>`).join('');
}

const CHANNEL_DATA = [
  { name: '微信社群', users: 2100, convRate: '6.4%', revenue: 28600, cac: 42, ltv: 620, score: 82, trend: '▲', trendCls: 'trend-up' },
  { name: '内容合作', users: 1400, convRate: '4.8%', revenue: 19200, cac: 56, ltv: 540, score: 74, trend: '▲', trendCls: 'trend-up' },
  { name: '小红书', users: 980, convRate: '3.6%', revenue: 13600, cac: 48, ltv: 420, score: 68, trend: '▲', trendCls: 'trend-up' },
  { name: '转介绍', users: 620, convRate: '12.1%', revenue: 24800, cac: 18, ltv: 860, score: 93, trend: '▲', trendCls: 'trend-up' },
  { name: '直接流量', users: 300, convRate: '15.0%', revenue: 16800, cac: 12, ltv: 940, score: 96, trend: '▲', trendCls: 'trend-up' },
];

const MONTHS_12 = ['2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06'];
const MONTHS_12_LABEL = MONTHS_12.map((month) => month.slice(5) + '月');

const CHANNEL_MONTHLY = [
  [120, 136, 148, 165, 172, 186, 194, 201, 214, 228, 241, 252],
  [82, 88, 94, 102, 110, 118, 126, 132, 139, 148, 156, 164],
  [56, 62, 68, 72, 79, 84, 88, 93, 96, 102, 108, 112],
  [28, 34, 38, 42, 45, 48, 52, 56, 60, 64, 68, 72],
  [12, 16, 18, 20, 23, 24, 26, 29, 31, 34, 36, 39],
];

function renderChannelSection() {
  const kpiContainer = document.getElementById('channel-kpi-cards');
  if (kpiContainer) {
    kpiContainer.innerHTML = CHANNEL_DATA.map((channel) => `
      <div class="kpi-card">
        <div class="kpi-label">${channel.name}</div>
        <div class="kpi-value" style="font-size:20px">${channel.users}</div>
        <div class="kpi-sub">转化率 ${channel.convRate}</div>
        <div class="kpi-sub">营收 ¥${channel.revenue}</div>
        <div class="kpi-badge ${channel.trendCls === 'trend-up' ? 'kpi-badge-up' : 'kpi-badge-down'}">
          CAC ¥${channel.cac} · LTV ¥${channel.ltv}
        </div>
      </div>`).join('');
  }

  renderChart('channelStackedBar', {
    color: CHANNEL_COLORS,
    tooltip: baseTooltip((params) => {
      const list = Array.isArray(params) ? params : [params];
      return [`<div style="font-weight:700;margin-bottom:6px">${list[0].axisValueLabel}</div>`]
        .concat(list.map((item) => `${item.marker}${item.seriesName}：${item.value}`))
        .join('<br>');
    }),
    legend: baseLegend({ top: 0 }),
    grid: baseGrid({ top: 36, left: 18, right: 18, bottom: 54 }),
    dataZoom: timeZoom(MONTHS_12_LABEL),
    xAxis: {
      type: 'category',
      data: MONTHS_12_LABEL,
      ...baseAxis({ splitLine: { show: false } }),
    },
    yAxis: {
      type: 'value',
      ...baseAxis(),
    },
    series: CHANNEL_DATA.map((channel, index) => ({
      name: channel.name,
      type: 'bar',
      stack: 'total',
      data: CHANNEL_MONTHLY[index],
      barWidth: '44%',
      itemStyle: {
        color: window.GangtiseEcharts.rgba(CHANNEL_COLORS[index], 0.82),
        borderRadius: [4, 4, 0, 0],
      },
    })),
  });

  renderChart('cacLtvScatter', makeBubbleOption(
    CHANNEL_DATA.map((channel, index) => ({
      name: channel.name,
      users: channel.users,
      cac: channel.cac,
      ltv: channel.ltv,
      color: CHANNEL_COLORS[index],
    })),
  ));

  const tbody = document.getElementById('channel-quality-body');
  if (tbody) {
    tbody.innerHTML = CHANNEL_DATA.map((channel) => {
      const barW = Math.round(channel.score * 0.8);
      return `<tr>
        <td style="color:var(--text-main);font-weight:600">${channel.name}</td>
        <td>${channel.users}</td>
        <td>¥${channel.cac}</td>
        <td>¥${channel.ltv}</td>
        <td>${channel.convRate}</td>
        <td>
          <span class="score-bar" style="width:${barW}px"></span>
          <span style="color:var(--gold);font-weight:600">${channel.score}</span>
        </td>
        <td class="${channel.trendCls}">${channel.trend}</td>
      </tr>`;
    }).join('');
  }
}

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
  const kpiContainer = document.getElementById('kol-kpi-cards');
  if (kpiContainer) {
    const totalGmv = KOL_TOP10.reduce((sum, item) => sum + item.gmv, 0);
    const totalKols = 12;
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
        <div class="kpi-value">15.3%</div>
        <div class="kpi-badge kpi-badge-gold">加权平均</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">当前最佳样本</div>
        <div class="kpi-value" style="font-size:18px">${topKol}</div>
        <div class="kpi-badge kpi-badge-gold">种子作者</div>
      </div>`;
  }

  renderChart('kolTop10Bar', makeHorizontalBarOption(
    KOL_TOP10.map((item) => item.name),
    [{
      name: '试点收入 (元)',
      data: KOL_TOP10.map((item) => item.gmv),
      color: currentPalette().gold,
    }],
    { valueFormatter: '¥{value}' },
  ));

  renderChart('kolTierGrowth', {
    color: ['#FFD700', currentPalette().gold, currentPalette().gray],
    tooltip: baseTooltip((params) => {
      const list = Array.isArray(params) ? params : [params];
      return [`<div style="font-weight:700;margin-bottom:6px">${list[0].axisValueLabel}</div>`]
        .concat(list.map((item) => `${item.marker}${item.seriesName}：${item.value}`))
        .join('<br>');
    }),
    legend: baseLegend({ top: 0 }),
    grid: baseGrid({ top: 36, left: 18, right: 18, bottom: 54 }),
    dataZoom: timeZoom(MONTHS_12_LABEL),
    xAxis: {
      type: 'category',
      data: MONTHS_12_LABEL,
      ...baseAxis({ splitLine: { show: false } }),
    },
    yAxis: {
      type: 'value',
      ...baseAxis(),
    },
    series: [
      { name: 'S级', type: 'line', smooth: true, symbol: 'circle', symbolSize: 7, data: KOL_TIER_GROWTH.S, lineStyle: { width: 2.5, color: '#FFD700' }, areaStyle: { color: 'rgba(255,215,0,0.10)' }, itemStyle: { color: '#FFD700' } },
      { name: 'A级', type: 'line', smooth: true, symbol: 'circle', symbolSize: 7, data: KOL_TIER_GROWTH.A, lineStyle: { width: 2.5, color: currentPalette().gold }, areaStyle: { color: window.GangtiseEcharts.rgba(currentPalette().gold, 0.10) }, itemStyle: { color: currentPalette().gold } },
      { name: 'B级', type: 'line', smooth: true, symbol: 'circle', symbolSize: 7, data: KOL_TIER_GROWTH.B, lineStyle: { width: 2.5, color: currentPalette().gray }, areaStyle: { color: 'rgba(154,149,144,0.08)' }, itemStyle: { color: currentPalette().gray } },
    ],
  });

  renderChart('kolTierDonut', makeDonutOption(
    ['S级', 'A级', 'B级'],
    [2, 5, 10],
    ['#FFD700', currentPalette().gold, currentPalette().gray],
    { center: ['38%', '50%'] },
  ));

  const kolBody = document.getElementById('kol-table-body');
  if (kolBody) {
    kolBody.innerHTML = KOL_TOP10.slice(0, 8).map((item) => {
      const tierCls = item.tier === 'S' ? 'kol-tier-s' : item.tier === 'A' ? 'kol-tier-a' : 'kol-tier-b';
      const trendColor = item.trend.startsWith('+') ? '#2ECC71' : '#E74C3C';
      return `<tr>
        <td style="color:var(--text-main);font-weight:600">${item.name}</td>
        <td>${item.platform}</td>
        <td>${item.fans}</td>
        <td style="color:var(--gold);font-weight:600">¥${item.gmv}</td>
        <td>${item.rate}</td>
        <td><span class="${tierCls}">${item.tier}级</span></td>
        <td style="color:${trendColor}">${item.trend}</td>
      </tr>`;
    }).join('');
  }
}

const REVENUE_MONTHLY = [18000, 22400, 26800, 31200, 35600, 40200, 44800, 49200, 53800, 58600, 63400, 68800];
const USERS_MONTHLY = [180, 238, 286, 332, 388, 446, 504, 566, 628, 688, 742, 806];

const TIER_REVENUE = {
  '免费': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  '验证版会员': [6200, 7400, 8600, 9800, 11200, 12600, 13800, 15100, 16200, 17400, 18600, 19800],
  '专业会员': [8400, 10800, 13200, 15400, 17600, 19800, 22400, 24600, 27200, 29600, 32200, 34800],
  '机构试点': [3400, 4200, 5000, 6000, 6800, 7800, 8600, 9500, 10400, 11600, 12600, 14000],
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

  renderChart('revGmvUsers', makeVerticalBarOption(MONTHS_12_LABEL, [
    { name: 'MRR (元)', type: 'bar', data: REVENUE_MONTHLY, color: window.GangtiseEcharts.rgba(currentPalette().gold, 0.82), yAxisIndex: 0 },
    { name: '付费用户数', type: 'line', data: USERS_MONTHLY, color: currentPalette().blue, yAxisIndex: 1 },
  ], {
    zoom: true,
    rightAxis: true,
    leftFormatter: '¥{value}',
    rightFormatter: '{value}',
  }));

  renderChart('revTierStack', makeStackedAreaOption(
    MONTHS_12_LABEL,
    Object.keys(TIER_REVENUE).map((name, index) => ({
      name,
      data: TIER_REVENUE[name],
      color: ['#5A5650', currentPalette().blue, currentPalette().green, currentPalette().gold][index],
    })),
  ));

  renderChart('revChannelBar', makeVerticalBarOption(
    CHANNEL_DATA.map((item) => item.name),
    [{
      name: '月度营收（元）',
      type: 'bar',
      data: CHANNEL_DATA.map((item) => item.revenue),
      color: currentPalette().blue,
      yAxisIndex: 0,
    }],
    { leftFormatter: '¥{value}' },
  ));

  const thead = document.getElementById('cohort-thead');
  const tbody = document.getElementById('cohort-tbody');
  if (thead && tbody) {
    thead.innerHTML = '<th>队列</th>' + ['M0', 'M1', 'M2', 'M3', 'M4', 'M5'].map((item) => `<th>${item}</th>`).join('');
    tbody.innerHTML = COHORT_DATA.map((row) => {
      const cells = row.data.map((value) => {
        if (value === null) return '<td style="color:var(--gray-600)">—</td>';
        const intensity = value / 100;
        const bg = `rgba(200,169,110,${(intensity * 0.5 + 0.05).toFixed(2)})`;
        const color = intensity > 0.6 ? '#0D1B2A' : '#F8F6F0';
        return `<td style="background:${bg};color:${color};font-weight:600">${value}%</td>`;
      }).join('');
      return `<tr><td style="color:var(--gold);font-weight:600">${row.cohort}</td>${cells}</tr>`;
    }).join('');
  }
}

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
  const funnelContainer = document.getElementById('seg-funnel-container');
  if (funnelContainer) {
    const tiers = [
      { label: '免费用户', count: 1268, color: '#4A5568', convFrom: null, convTo: '16.9%' },
      { label: '验证版会员', count: 214, color: '#3182CE', convFrom: '16.9%', convTo: '59.8%' },
      { label: '专业会员', count: 128, color: '#38A169', convFrom: '59.8%', convTo: '26.6%' },
      { label: '机构试点', count: 34, color: '#C8A96E', convFrom: '26.6%', convTo: null },
    ];
    const maxCount = tiers[0].count;
    funnelContainer.innerHTML = tiers.map((tier) => {
      const width = Math.round((tier.count / maxCount) * 80) + 20;
      return `<div style="margin:8px auto;width:${width}%;max-width:800px;background:${tier.color}22;border:1px solid ${tier.color}66;border-radius:6px;padding:12px 20px;display:flex;align-items:center;justify-content:space-between;transition:all 0.3s">
        <div style="font-weight:600;color:${tier.color};font-size:14px">${tier.label}</div>
        <div style="color:var(--text-main);font-size:16px;font-weight:700">${tier.count.toLocaleString()}</div>
        <div style="color:var(--text-sub);font-size:12px">${tier.convFrom ? '付费转化 ' + tier.convFrom : '总注册用户'}</div>
      </div>
      ${tier.convTo ? '<div style="text-align:center;color:var(--gold);font-size:12px;margin:2px 0">↓ 转化率 ' + tier.convTo + '</div>' : ''}`;
    }).join('');
  }

  renderChart('segTierDonut', makeDonutOption(
    SEG_TIERS.map((item) => item.name),
    SEG_TIERS.map((item) => item.count),
    SEG_TIERS.map((item) => item.color),
    { center: ['38%', '50%'] },
  ));

  renderChart('segArpuBar', makeVerticalBarOption(
    SEG_TIERS.filter((item) => item.arpu > 0).map((item) => item.name),
    [{
      name: 'ARPU (¥/月)',
      type: 'bar',
      data: SEG_TIERS.filter((item) => item.arpu > 0).map((item) => item.arpu),
      color: currentPalette().blue,
      yAxisIndex: 0,
    }],
    { leftFormatter: '¥{value}' },
  ));

  const flowContainer = document.getElementById('lifecycle-flow');
  if (flowContainer) {
    flowContainer.innerHTML = LIFECYCLE_STAGES.map((stage, index) => `
      ${index > 0 ? '<div class="lifecycle-arrow">→</div>' : ''}
      <div class="lifecycle-stage">
        <div class="lifecycle-icon">${stage.icon}</div>
        <div class="lifecycle-name">${stage.name}</div>
        <div class="lifecycle-desc">${stage.desc}</div>
        <div class="lifecycle-num">${stage.num}</div>
      </div>`).join('');
  }

  const retentionBody = document.getElementById('retention-body');
  if (retentionBody) {
    retentionBody.innerHTML = SEG_TIERS.map((tier) => {
      const r7Color = parseInt(tier.r7, 10) > 70 ? '#2ECC71' : parseInt(tier.r7, 10) > 40 ? currentPalette().gold : '#E74C3C';
      const r30Color = parseInt(tier.r30, 10) > 60 ? '#2ECC71' : parseInt(tier.r30, 10) > 30 ? currentPalette().gold : '#E74C3C';
      const r90Color = parseInt(tier.r90, 10) > 50 ? '#2ECC71' : parseInt(tier.r90, 10) > 20 ? currentPalette().gold : '#E74C3C';
      return `<tr>
        <td style="color:${tier.color};font-weight:600">${tier.name}</td>
        <td>${tier.count.toLocaleString()}</td>
        <td style="color:${r7Color};font-weight:600">${tier.r7}</td>
        <td style="color:${r30Color};font-weight:600">${tier.r30}</td>
        <td style="color:${r90Color};font-weight:600">${tier.r90}</td>
        <td style="color:var(--gold)">${tier.arpu > 0 ? '¥' + tier.arpu : '—'}</td>
        <td style="color:var(--gold)">${tier.ltv > 0 ? '¥' + tier.ltv.toLocaleString() : '—'}</td>
      </tr>`;
    }).join('');
  }
}

window.initDashboardCharts = initDashboardCharts;
window.showDashSection = showDashSection;
window.setDateRange = setDateRange;

document.addEventListener('gangtise:themechange', () => {
  const active = getActiveDashSection();
  if (active) {
    rerenderDashboardSection(active);
  }
});

document.addEventListener('DOMContentLoaded', () => {
  if (window.AUTO_INIT_DASHBOARD === false) return;
  if (document.getElementById('ds-funnel')) showDashSection(window.dashboardDefaultSection || 'funnel');
});
