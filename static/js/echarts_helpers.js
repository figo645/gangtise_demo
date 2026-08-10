(function (global) {
  const registry = new Map();
  const resizeRegistry = new Map();
  const pendingTasks = [];
  let flushScheduled = false;

  function cssVar(name, fallback) {
    try {
      const value = getComputedStyle(document.body).getPropertyValue(name).trim();
      return value || fallback;
    } catch (error) {
      return fallback;
    }
  }

  function palette() {
    return {
      gold: cssVar('--gold', '#C8A96E'),
      goldLight: cssVar('--gold-light', '#E2C98A'),
      goldDark: cssVar('--gold-dark', '#A8893E'),
      navy: cssVar('--navy', '#0D1B2A'),
      navyMid: cssVar('--navy-mid', '#1A2E45'),
      navyLight: cssVar('--navy-light', '#294766'),
      white: cssVar('--white', '#F8F6F0'),
      textMain: cssVar('--text-main', '#182132'),
      textSub: cssVar('--text-sub', '#5A6572'),
      surface: cssVar('--surface', '#FFFFFF'),
      surface2: cssVar('--surface-2', '#F3F8FE'),
      border: cssVar('--border-soft', 'rgba(47,116,192,0.12)'),
      gray: cssVar('--gray-400', '#9A9590'),
      blue: '#2F74C0',
      blueSoft: 'rgba(47,116,192,0.16)',
      green: '#2ECC71',
      red: '#E74C3C',
      purple: '#AF7AC5',
      yellow: '#F6C453',
    };
  }

  function rgba(hex, alpha) {
    if (!hex || typeof hex !== 'string') return `rgba(47,116,192,${alpha})`;
    const raw = hex.replace('#', '').trim();
    const normalized = raw.length === 3
      ? raw.split('').map((char) => char + char).join('')
      : raw;
    const value = parseInt(normalized, 16);
    if (!Number.isFinite(value)) return `rgba(47,116,192,${alpha})`;
    const r = (value >> 16) & 255;
    const g = (value >> 8) & 255;
    const b = value & 255;
    return `rgba(${r},${g},${b},${alpha})`;
  }

  function nextId(prefix) {
    return `${prefix || 'gt-chart'}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function ensureContainer(target) {
    const element = typeof target === 'string' ? document.getElementById(target) : target;
    if (!element) return null;
    if (element.tagName && element.tagName.toLowerCase() === 'canvas') {
      const replacement = document.createElement('div');
      replacement.id = element.id;
      replacement.className = element.className;
      replacement.style.cssText = element.style.cssText;
      if (!replacement.style.width) replacement.style.width = '100%';
      if (!replacement.style.height) replacement.style.height = '100%';
      if (!replacement.style.minHeight) replacement.style.minHeight = '220px';
      replacement.dataset.echartsHost = 'true';
      element.replaceWith(replacement);
      return replacement;
    }
    element.dataset.echartsHost = 'true';
    if (!element.style.width) element.style.width = '100%';
    return element;
  }

  function getKey(target) {
    if (typeof target === 'string') return target;
    return target && target.id ? target.id : '';
  }

  function clearResizeBinding(key) {
    const item = resizeRegistry.get(key);
    if (!item) return;
    if (item.observer && typeof item.observer.disconnect === 'function') item.observer.disconnect();
    if (item.listener) global.removeEventListener('resize', item.listener);
    resizeRegistry.delete(key);
  }

  function bindResize(key, chart, container) {
    clearResizeBinding(key);
    const listener = () => {
      if (chart && typeof chart.resize === 'function') chart.resize();
    };
    global.addEventListener('resize', listener);
    let observer = null;
    if (typeof ResizeObserver !== 'undefined' && container) {
      observer = new ResizeObserver(() => {
        if (chart && typeof chart.resize === 'function') chart.resize();
      });
      observer.observe(container);
    }
    resizeRegistry.set(key, { listener, observer });
  }

  function getChartSize(container) {
    return {
      width: Math.max(Number(container && container.clientWidth) || 0, 1),
      height: Math.max(Number(container && container.clientHeight) || 0, 1),
    };
  }

  function dispose(target) {
    const key = getKey(target);
    if (!key) return;
    const chart = registry.get(key);
    if (chart && typeof chart.dispose === 'function' && !chart.isDisposed()) {
      chart.dispose();
    }
    registry.delete(key);
    clearResizeBinding(key);
  }

  function render(target, option, extra) {
    const container = ensureContainer(target);
    if (!container) return null;
    if (!global.echarts) {
      container.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#7B92AA;font-size:12px">ECharts 未加载</div>';
      return null;
    }
    const key = getKey(container);
    const current = registry.get(key);
    const isCurrentContainer = current
      && !current.isDisposed()
      && typeof current.getDom === 'function'
      && current.getDom() === container;
    if (current && !isCurrentContainer) {
      // Dynamic pages can replace a chart node while retaining its id. An
      // instance tied to the detached node would otherwise consume updates.
      if (!current.isDisposed() && typeof current.dispose === 'function') current.dispose();
      registry.delete(key);
      clearResizeBinding(key);
    }
    // A chart can be prepared while its tab is display:none. Initializing at
    // 0x0 leaves a blank canvas even after the tab becomes visible.
    const size = getChartSize(container);
    const chart = isCurrentContainer
      ? current
      : global.echarts.init(container, null, { renderer: 'canvas', width: size.width, height: size.height });
    registry.set(key, chart);
    chart.clear();
    chart.setOption(option || {}, true);
    chart.off('click');
    if (extra && typeof extra.onClick === 'function') chart.on('click', extra.onClick);
    bindResize(key, chart, container);
    global.requestAnimationFrame(() => {
      if (chart && !chart.isDisposed() && typeof chart.resize === 'function') chart.resize();
    });
    return chart;
  }

  function tooltipBase(customFormatter) {
    const p = palette();
    return {
      trigger: 'axis',
      backgroundColor: '#FFFFFF',
      borderColor: rgba(p.blue, 0.22),
      borderWidth: 1,
      textStyle: { color: p.textMain, fontSize: 12 },
      extraCssText: 'box-shadow:0 14px 30px rgba(31,73,125,0.14);border-radius:12px;padding:10px 12px;',
      axisPointer: { type: 'cross', lineStyle: { color: rgba(p.blue, 0.25) } },
      formatter: customFormatter,
    };
  }

  function axisBase(overrides) {
    const p = palette();
    return Object.assign({
      axisLine: { lineStyle: { color: rgba(p.blue, 0.16) } },
      axisLabel: { color: p.textSub, fontSize: 11 },
      splitLine: { lineStyle: { color: rgba(p.blue, 0.08) } },
      axisTick: { show: false },
    }, overrides || {});
  }

  function legendBase(overrides) {
    const p = palette();
    return Object.assign({
      top: 0,
      icon: 'roundRect',
      itemWidth: 12,
      itemHeight: 6,
      textStyle: { color: p.textSub, fontSize: 11 },
    }, overrides || {});
  }

  function gridBase(overrides) {
    return Object.assign({ top: 36, left: 12, right: 18, bottom: 54, containLabel: true }, overrides || {});
  }

  function normalizeMaSeries(candles, series) {
    const list = Array.isArray(series) ? series : [];
    return candles.map((candle) => {
      const found = list.find((item) => item && item.date === candle.date);
      return found ? Number(found.value || 0) : null;
    });
  }

  function normalizeKlineTooltipValues(rawValue) {
    const values = Array.isArray(rawValue) ? rawValue : [];
    if (values.length >= 5) {
      return {
        open: values[1],
        close: values[2],
        low: values[3],
        high: values[4],
      };
    }
    return {
      open: values[0],
      close: values[1],
      low: values[2],
      high: values[3],
    };
  }

  function formatTooltipMetric(value) {
    if (value === null || value === undefined || value === '') return '--';
    if (Number.isNaN(Number(value))) return '--';
    return value;
  }

  function buildKlineOption(payload, config) {
    const p = palette();
    const safeConfig = config || {};
    const candles = Array.isArray(payload && payload.candles) ? payload.candles : [];
    const anomalies = Array.isArray(payload && payload.anomalies) ? payload.anomalies : [];
    const annotations = Array.isArray(safeConfig.annotations) ? safeConfig.annotations : [];
    const categories = candles.map((item) => String(item.date || '').slice(5) || '--');
    const candleData = candles.map((item) => [
      Number(item.open || 0),
      Number(item.close || 0),
      Number(item.low || 0),
      Number(item.high || 0),
    ]);
    const ma5 = normalizeMaSeries(candles, payload && payload.ma5);
    const ma10 = normalizeMaSeries(candles, payload && payload.ma10);
    const ma20 = normalizeMaSeries(candles, payload && payload.ma20);
    const anomalySeries = anomalies.map((item) => {
      const index = candles.findIndex((candle) => candle.date === item.date);
      return {
        value: [index, Number(item.value || 0)],
        label: item.label || '异动',
      };
    }).filter((item) => item.value[0] >= 0);
    const annotationSeries = annotations.map((item) => {
      const index = Number(item.candleIndex);
      const candle = candles[index];
      return candle ? {
        value: [index, Number(candle.high || candle.close || 0)],
        title: item.content || item.title || '复盘标注',
        note: item.content || item.note || '',
        trigger: '',
      } : null;
    }).filter(Boolean);
    return {
      animationDuration: 280,
      color: [p.yellow, p.blue, p.purple],
      legend: legendBase({ selectedMode: false }),
      grid: gridBase(),
      tooltip: tooltipBase((params) => {
        const main = Array.isArray(params) ? params.find((item) => item.seriesType === 'candlestick') : params;
        if (!main || !Array.isArray(main.value)) return '';
        const value = normalizeKlineTooltipValues(main.value);
        const lines = [
          `<div style="font-weight:700;color:${p.textMain};margin-bottom:6px">${main.axisValueLabel || main.name || '--'}</div>`,
          `开盘：${formatTooltipMetric(value.open)}`,
          `收盘：${formatTooltipMetric(value.close)}`,
          `最低：${formatTooltipMetric(value.low)}`,
          `最高：${formatTooltipMetric(value.high)}`,
        ];
        (Array.isArray(params) ? params : []).forEach((item) => {
          if (item.seriesName && item.seriesType === 'line' && item.value !== null && item.value !== undefined) {
            const lineValue = Array.isArray(item.value) ? item.value[item.value.length - 1] : item.value;
            lines.push(`${item.marker}${item.seriesName}：${formatTooltipMetric(lineValue)}`);
          }
        });
        return lines.join('<br>');
      }),
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      dataZoom: [
        { type: 'inside', xAxisIndex: [0], zoomLock: !!safeConfig.zoomLock },
        { type: 'slider', xAxisIndex: [0], height: 18, bottom: 14, borderColor: 'transparent', backgroundColor: rgba(p.blue, 0.05), fillerColor: rgba(p.blue, 0.14), handleSize: 0 },
      ],
      xAxis: {
        type: 'category',
        data: categories,
        boundaryGap: true,
        min: 'dataMin',
        max: 'dataMax',
        ...axisBase({ splitLine: { show: false } }),
      },
      yAxis: {
        type: 'value',
        scale: true,
        ...axisBase(),
      },
      series: [
        {
          name: safeConfig.candleLabel || 'K线',
          type: 'candlestick',
          data: candleData,
          itemStyle: {
            color: p.red,
            color0: p.green,
            borderColor: p.red,
            borderColor0: p.green,
          },
        },
        {
          name: 'MA5',
          type: 'line',
          data: ma5,
          smooth: true,
          symbol: 'none',
          connectNulls: false,
          lineStyle: { width: 1.8, color: p.yellow },
        },
        {
          name: 'MA10',
          type: 'line',
          data: ma10,
          smooth: true,
          symbol: 'none',
          connectNulls: false,
          lineStyle: { width: 1.8, color: p.blue },
        },
        {
          name: 'MA20',
          type: 'line',
          data: ma20,
          smooth: true,
          symbol: 'none',
          connectNulls: false,
          lineStyle: { width: 1.8, color: p.purple },
        },
        {
          name: '异动',
          type: 'scatter',
          data: anomalySeries,
          symbolSize: 12,
          itemStyle: { color: rgba(p.red, 0.16), borderColor: p.red, borderWidth: 1.5 },
          label: {
            show: true,
            position: 'top',
            formatter: (params) => (params.data && params.data.label) || '异动',
            color: p.red,
            fontSize: 10,
          },
          tooltip: { trigger: 'item' },
        },
        {
          name: '标注',
          type: 'scatter',
          data: annotationSeries,
          symbol: 'circle',
          symbolSize: 13,
          itemStyle: { color: p.blue, borderColor: '#FFFFFF', borderWidth: 2 },
          label: {
            show: true,
            formatter: '注',
            color: '#FFFFFF',
            fontSize: 9,
            fontWeight: 700,
          },
          tooltip: {
            trigger: 'item',
            backgroundColor: '#FFFFFF',
            borderColor: rgba(p.blue, 0.22),
            textStyle: { color: p.textMain, fontSize: 12 },
            formatter: (params) => {
              const data = params.data || {};
              return [
                `<div style="font-weight:700;margin-bottom:6px">${data.title || 'K线标注'}</div>`,
                data.note || '暂无说明',
                data.trigger ? `验证节点：${data.trigger}` : '',
              ].filter(Boolean).join('<br>');
            },
          },
        },
      ],
    };
  }

  function buildLineOption(series, config) {
    const p = palette();
    const rows = Array.isArray(series) ? series : [];
    const safeConfig = config || {};
    const data = rows.map((item) => Number(item.value || 0));
    const categories = rows.map((item) => String(item.date || item.label || '').slice(5) || '--');
    return {
      animationDuration: 260,
      color: [safeConfig.lineColor || p.blue],
      grid: gridBase({ top: 28, bottom: 52 }),
      tooltip: tooltipBase((params) => {
        const item = Array.isArray(params) ? params[0] : params;
        return `<div style="font-weight:700;color:${p.textMain};margin-bottom:6px">${item.axisValueLabel || '--'}</div>${safeConfig.valueLabel || '数值'}：${item.value}`;
      }),
      dataZoom: [
        { type: 'inside', xAxisIndex: [0] },
        { type: 'slider', xAxisIndex: [0], height: 18, bottom: 12, borderColor: 'transparent', backgroundColor: rgba(p.blue, 0.05), fillerColor: rgba(p.blue, 0.14), handleSize: 0 },
      ],
      xAxis: {
        type: 'category',
        data: categories,
        ...axisBase({ splitLine: { show: false } }),
      },
      yAxis: {
        type: 'value',
        scale: true,
        ...axisBase(),
      },
      series: [
        {
          name: safeConfig.seriesName || '趋势',
          type: 'line',
          data,
          smooth: true,
          symbol: data.length > 24 ? 'none' : 'circle',
          symbolSize: 7,
          lineStyle: { width: 2.5, color: safeConfig.lineColor || p.blue },
          itemStyle: { color: safeConfig.lineColor || p.blue },
          areaStyle: { color: rgba(safeConfig.lineColor || p.blue, 0.12) },
        },
      ],
    };
  }

  function buildDistributionOption(values, config) {
    const p = palette();
    const safeConfig = config || {};
    const list = Array.isArray(values) ? values.map((item) => Number(item)).filter((item) => Number.isFinite(item)) : [];
    if (!list.length) return { series: [] };
    const bucketCount = Math.min(8, Math.max(4, Math.floor(Math.sqrt(list.length))));
    const min = Math.min.apply(null, list);
    const max = Math.max.apply(null, list);
    const span = Math.max(max - min, 1);
    const bucketSize = span / bucketCount;
    const buckets = Array.from({ length: bucketCount }, function (_, index) {
      return {
        label: `${(min + bucketSize * index).toFixed(1)}-${(min + bucketSize * (index + 1)).toFixed(1)}`,
        value: 0,
      };
    });
    list.forEach((value) => {
      const rawIndex = Math.floor((value - min) / bucketSize);
      const bucketIndex = Math.max(0, Math.min(bucketCount - 1, rawIndex));
      buckets[bucketIndex].value += 1;
    });
    return {
      animationDuration: 240,
      color: [safeConfig.barColor || p.blue],
      grid: gridBase({ top: 24, bottom: 44 }),
      tooltip: tooltipBase((params) => {
        const item = Array.isArray(params) ? params[0] : params;
        return `<div style="font-weight:700;color:${p.textMain};margin-bottom:6px">${item.axisValueLabel || '--'}</div>样本数：${item.value}`;
      }),
      xAxis: {
        type: 'category',
        data: buckets.map((item) => item.label),
        ...axisBase({ splitLine: { show: false }, axisLabel: { color: p.textSub, fontSize: 10, interval: 0, rotate: bucketCount > 5 ? 24 : 0 } }),
      },
      yAxis: {
        type: 'value',
        ...axisBase(),
      },
      series: [
        {
          name: safeConfig.seriesName || '分布统计',
          type: 'bar',
          data: buckets.map((item) => item.value),
          barWidth: '58%',
          itemStyle: {
            color: safeConfig.barColor || p.blue,
            borderRadius: [8, 8, 0, 0],
          },
        },
      ],
    };
  }

  function enqueue(chartId, mountFn) {
    pendingTasks.push({ chartId, mountFn });
    if (!flushScheduled) {
      flushScheduled = true;
      requestAnimationFrame(() => {
        flushScheduled = false;
        flush();
      });
    }
  }

  function flush(root) {
    for (let index = pendingTasks.length - 1; index >= 0; index -= 1) {
      const task = pendingTasks[index];
      const element = document.getElementById(task.chartId);
      if (!element) continue;
      if (root && !root.contains(element)) continue;
      try {
        task.mountFn(element);
      } catch (error) {
        console.error('ECharts mount failed', error);
      }
      pendingTasks.splice(index, 1);
    }
  }

  function resizeAll() {
    registry.forEach((chart) => {
      if (chart && !chart.isDisposed() && typeof chart.resize === 'function') chart.resize();
    });
  }

  global.GangtiseEcharts = {
    palette,
    rgba,
    nextId,
    ensureContainer,
    render,
    dispose,
    enqueue,
    flush,
    tooltipBase,
    axisBase,
    legendBase,
    gridBase,
    buildKlineOption,
    buildLineOption,
    buildDistributionOption,
    resizeAll,
  };
}(window));
