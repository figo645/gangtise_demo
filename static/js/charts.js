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
  const response = await fetch('/api/admin/funnel-analytics');
  const result = await response.json();
  if (!response.ok || !result.ok) return;
  const analytics = result.analytics || {};
  const funnelKpi = document.getElementById('funnel-kpi-cards');
  if (funnelKpi) {
    funnelKpi.innerHTML = (analytics.funnel || []).slice(0, 4).map((item) => `
      <div class="kpi-card">
        <div class="kpi-label">${item.layer}</div>
        <div class="kpi-value">${Number(item.count || 0).toLocaleString('zh-CN')}</div>
        <div class="kpi-badge kpi-badge-gold">真实记录</div>
      </div>`).join('') || '<div style="color:#8899aa">暂无真实漏斗数据。</div>';
  }
  renderFunnel(analytics.funnel || []);
  renderChannelDonut(analytics.channels || {});
  renderRevenueTrend(analytics.monthly || []);
  renderKolBar(analytics.kols || []);
  renderSegmentDonut(analytics.segments || []);
  renderChannelRevenue((analytics.channels || {}).rows || []);
  renderHeatmap(analytics.heatmap || []);
}

function renderFunnel(data) {
  const container = document.getElementById('funnel-container');
  if (!container) return;
  const maxCount = Number(data[0] && data[0].count) || 0;
  const minWidthPct = 32;
  container.innerHTML = data.map((item, index) => {
    const widthPct = maxCount ? Math.round((item.count / maxCount) * 100) : 0;
    const previousCount = index > 0 ? Number(data[index - 1].count) : 0;
    const dropRate = previousCount > 0 ? ((previousCount - item.count) / previousCount * 100).toFixed(1) : null;
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
  }).join('') || '<div style="color:var(--gray-400);padding:20px">暂无真实漏斗数据。</div>';
}

function renderChannelDonut(payload) {
  const data = Array.isArray(payload) ? payload : (payload.rows || []);
  const target = document.getElementById('channelDonut');
  if (!target) return;
  renderChart(target, makeDonutOption(
    data.map((item) => item.name),
    data.map((item) => item.users),
    data.map((item, index) => item.color || CHANNEL_COLORS[index % CHANNEL_COLORS.length]),
    { center: ['38%', '50%'] },
  ));
}

function renderRevenueTrend(data) {
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

function renderKolBar(data) {
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

function renderSegmentDonut(data) {
  const target = document.getElementById('segmentDonut');
  if (!target) return;
  renderChart(target, makeDonutOption(
    data.map((item) => item.segment || item.name),
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
        <div class="segment-pct">${data.reduce((sum, entry) => sum + Number(entry.count || 0), 0) ? (Number(item.count || 0) / data.reduce((sum, entry) => sum + Number(entry.count || 0), 0) * 100).toFixed(1) : '0.0'}%</div>
      </div>`).join('');
  }
}

function renderChannelRevenue(data) {
  const target = document.getElementById('channelRevenue');
  if (!target) return;
  const labels = data.map((item) => item.name);
  renderChart(target, makeVerticalBarOption(labels, [
    { name: '月度营收 (元)', type: 'bar', data: data.map((item) => item.revenue), color: currentPalette().blue, yAxisIndex: 0 },
  ], {
    leftFormatter: '¥{value}',
  }));
}

function renderHeatmap(data) {
  const tbody = document.getElementById('heatmap-body');
  if (!tbody) return;
  tbody.innerHTML = data.map((item) => `
    <tr>
      <td style="color:var(--text-main);font-weight:600">${item.channel}</td>
      ${(item.values || []).map((value, cellIndex) => {
        const intensity = cellIndex === 0 ? 0.08 : Math.min(value / (cellIndex === 1 ? 45 : cellIndex === 2 ? 15 : cellIndex === 3 ? 10 : 2.5), 1);
        const bg = `rgba(200,169,110,${(intensity * 0.6 + 0.05).toFixed(2)})`;
        const color = intensity > 0.5 ? '#0D1B2A' : '#F8F6F0';
        return `<td style="background:${bg};color:${color};font-weight:${intensity > 0.4 ? '600' : '400'};text-align:center">${value}%</td>`;
      }).join('')}
    </tr>`).join('') || '<tr><td colspan="6" style="color:#8899aa;text-align:center">暂无真实渠道转化数据。</td></tr>';
}

async function renderChannelSection() {
  const response = await fetch('/api/admin/channels');
  const result = await response.json();
  if (!response.ok || !result.ok) return;
  const channelRows = Array.isArray((result.channels || {}).rows) ? result.channels.rows : [];
  const kpiContainer = document.getElementById('channel-kpi-cards');
  if (kpiContainer) {
    kpiContainer.innerHTML = channelRows.map((channel) => `
      <div class="kpi-card">
        <div class="kpi-label">${channel.name}</div>
        <div class="kpi-value" style="font-size:20px">${channel.users}</div>
        <div class="kpi-sub">付费转化率 ${Number(channel.conversion || 0).toFixed(1)}%</div>
        <div class="kpi-sub">营收 ¥${channel.revenue}</div>
        <div class="kpi-badge kpi-badge-gold">${Number(channel.paid_users || 0)} 位付费用户</div>
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
    dataZoom: [],
    xAxis: {
      type: 'category',
      data: ['当前'],
      ...baseAxis({ splitLine: { show: false } }),
    },
    yAxis: {
      type: 'value',
      ...baseAxis(),
    },
    series: channelRows.map((channel, index) => ({
      name: channel.name,
      type: 'bar',
      stack: 'total',
      data: [channel.users],
      barWidth: '44%',
      itemStyle: {
        color: window.GangtiseEcharts.rgba(CHANNEL_COLORS[index], 0.82),
        borderRadius: [4, 4, 0, 0],
      },
    })),
  });

  const scatterTarget = document.getElementById('cacLtvScatter');
  if (scatterTarget) scatterTarget.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#8899aa;font-size:12px">暂无真实 CAC / LTV 数据</div>';

  const tbody = document.getElementById('channel-quality-body');
  if (tbody) {
    tbody.innerHTML = channelRows.map((channel) => {
      return `<tr>
        <td style="color:var(--text-main);font-weight:600">${channel.name}</td>
        <td>${channel.users}</td>
        <td>--</td>
        <td>--</td>
        <td>${Number(channel.conversion || 0).toFixed(1)}%</td>
        <td>--</td>
        <td>--</td>
      </tr>`;
    }).join('');
  }
}

async function renderKolSection() {
  const response = await fetch('/api/admin/kol-analytics');
  const result = await response.json();
  if (!response.ok || !result.ok) return;
  const analytics = result.analytics || {};
  const kolRows = Array.isArray(analytics.rows) ? analytics.rows : [];
  const kpiContainer = document.getElementById('kol-kpi-cards');
  if (kpiContainer) {
    const totalGmv = Number(analytics.total_revenue || 0);
    const totalKols = Number(analytics.total_kols || 0);
    const topKol = analytics.top_kol || '--';
    kpiContainer.innerHTML = `
      <div class="kpi-card">
        <div class="kpi-label">试点作者总数</div>
        <div class="kpi-value">${totalKols}</div>
        <div class="kpi-badge kpi-badge-gold">真实租户数</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">试点协同收入</div>
        <div class="kpi-value">¥${totalGmv}</div>
        <div class="kpi-badge kpi-badge-gold">付费标注 × 单价</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">平均佣金率</div>
        <div class="kpi-value">${Number(analytics.average_rate || 0).toFixed(2)}%</div>
        <div class="kpi-badge kpi-badge-gold">已配置分成比例</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">当前最佳样本</div>
        <div class="kpi-value" style="font-size:18px">${topKol}</div>
        <div class="kpi-badge kpi-badge-gold">种子作者</div>
      </div>`;
  }

  renderChart('kolTop10Bar', makeHorizontalBarOption(
    kolRows.slice(0, 10).map((item) => item.name),
    [{
      name: '试点收入 (元)',
      data: kolRows.slice(0, 10).map((item) => item.gmv),
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
    dataZoom: timeZoom((analytics.months || []).map((month) => month.slice(5))),
    xAxis: {
      type: 'category',
      data: (analytics.months || []).map((month) => month.slice(5)),
      ...baseAxis({ splitLine: { show: false } }),
    },
    yAxis: {
      type: 'value',
      ...baseAxis(),
    },
    series: Object.keys(analytics.tier_growth || {}).map((tier, index) => ({
      name: tier,
      type: 'line',
      smooth: true,
      connectNulls: false,
      symbol: 'circle',
      symbolSize: 7,
      data: analytics.tier_growth[tier],
      lineStyle: { width: 2.5, color: [currentPalette().gold, currentPalette().blue, currentPalette().gray][index % 3] },
      itemStyle: { color: [currentPalette().gold, currentPalette().blue, currentPalette().gray][index % 3] },
    })),
  });

  const tierCounts = analytics.tier_counts || {};
  const tierLabels = Object.keys(tierCounts);
  renderChart('kolTierDonut', makeDonutOption(
    tierLabels,
    tierLabels.map((tier) => tierCounts[tier]),
    tierLabels.map((_, index) => ['#FFD700', currentPalette().gold, currentPalette().gray][index % 3]),
    { center: ['38%', '50%'] },
  ));

  const kolBody = document.getElementById('kol-table-body');
  if (kolBody) {
    kolBody.innerHTML = kolRows.slice(0, 8).map((item) => {
      const tierCls = item.tier === 'S' ? 'kol-tier-s' : item.tier === 'A' ? 'kol-tier-a' : 'kol-tier-b';
      const trendColor = item.trend && item.trend !== '--' ? '#2ECC71' : currentPalette().gray;
      return `<tr>
        <td style="color:var(--text-main);font-weight:600">${item.name}</td>
        <td>${item.platform}</td>
        <td>${item.fans}</td>
        <td style="color:var(--gold);font-weight:600">¥${item.gmv}</td>
        <td>${item.rate}</td>
        <td><span class="${tierCls}">${item.tier}级</span></td>
        <td style="color:${trendColor}">${item.trend || '--'}</td>
      </tr>`;
    }).join('');
  }
}

async function renderRevenueSection() {
  const response = await fetch('/api/admin/revenue-analytics');
  const result = await response.json();
  if (!response.ok || !result.ok) return;
  const analytics = result.analytics || {};
  const monthly = Array.isArray(analytics.monthly) ? analytics.monthly : [];
  const monthLabels = monthly.map((item) => String(item.month || '').slice(5));
  const kpiContainer = document.getElementById('revenue-kpi-cards');
  if (kpiContainer) {
    const mrr = Number(analytics.mrr || 0);
    const tenantCount = Number(analytics.active_tenants || 0);
    const averagePrice = Number(analytics.average_price || 0);
    kpiContainer.innerHTML = `
      <div class="kpi-card">
        <div class="kpi-label">本月协同收入</div>
        <div class="kpi-value">¥${mrr}</div>
        <div class="kpi-badge kpi-badge-gold">付费用户 × 租户单价</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">当前付费样本</div>
        <div class="kpi-value">${Number(analytics.paid_users || 0)}</div>
        <div class="kpi-badge kpi-badge-gold">真实用户标注</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">有定价租户</div>
        <div class="kpi-value">${tenantCount}</div>
        <div class="kpi-badge kpi-badge-gold">真实租户配置</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">平均单价</div>
        <div class="kpi-value">¥${averagePrice}</div>
        <div class="kpi-badge kpi-badge-gold">租户当前注册定价</div>
      </div>`;
  }

  renderChart('revGmvUsers', makeVerticalBarOption(monthLabels, [
    { name: 'MRR (元)', type: 'bar', data: monthly.map((item) => item.revenue), color: window.GangtiseEcharts.rgba(currentPalette().gold, 0.82), yAxisIndex: 0 },
    { name: '付费用户数', type: 'line', data: monthly.map((item) => item.users), color: currentPalette().blue, yAxisIndex: 1 },
  ], {
    zoom: true,
    rightAxis: true,
    leftFormatter: '¥{value}',
    rightFormatter: '{value}',
  }));

  renderChart('revTenantBar', makeHorizontalBarOption(
    (analytics.tenant_revenue || []).map((item) => item.name),
    [{
      name: '协同收入（元）',
      type: 'bar',
      data: (analytics.tenant_revenue || []).map((item) => item.revenue),
      color: currentPalette().blue,
    }],
    { valueFormatter: '¥{value}' },
  ));
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
