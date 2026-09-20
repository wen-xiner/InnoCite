/**
 * InnoCite 公共图表模块
 * 封装 Plotly 图表的默认样式和通用配置，消除各页面重复代码。
 *
 * 所有函数挂载在 window.InnoCite 命名空间下。
 */
window.InnoCite = window.InnoCite || {};

(function (ns) {
    "use strict";

    // ═══════════════════════════════════════════
    // 默认样式常量
    // ═══════════════════════════════════════════

    var COLOR_PALETTE = [
        "#0f3460", "#e94560", "#533483", "#00b4d8", "#ff6b6b",
        "#2d6a4f", "#d4a373", "#457b9d", "#f4a261", "#264653",
    ];

    var BASE_LAYOUT = {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "Inter, sans-serif", size: 11, color: "#6b7280" },
        margin: { l: 50, r: 30, t: 10, b: 40 },
        hovermode: "x unified",
        xaxis: {
            gridcolor: "rgba(0,0,0,.04)",
            linecolor: "rgba(0,0,0,.08)",
            tickfont: { size: 10, color: "#9ca3af" },
        },
        yaxis: {
            gridcolor: "rgba(0,0,0,.04)",
            linecolor: "rgba(0,0,0,.08)",
            tickfont: { size: 10, color: "#9ca3af" },
        },
        legend: {
            font: { size: 10, color: "#6b7280" },
        },
    };

    // ═══════════════════════════════════════════
    // 趋势曲线图
    // ═══════════════════════════════════════════

    /**
     * 根据 /api/trend 返回的数据创建关键词热度趋势曲线图。
     *
     * @param {string} containerId - 图表容器 DOM 元素 ID
     * @param {Array} trendData - 趋势数据，格式：
     *   [{ keyword: string, x: number[], y: number[], avg: number }, ...]
     * @param {Object} [options] - 可选配置
     * @param {string} [options.xTitle='年份'] - X 轴标题
     * @param {string} [options.yTitle='热度值'] - Y 轴标题
     * @param {number} [options.lineWidth=2.5] - 曲线宽度
     * @param {number} [options.markerSize=7] - 数据点大小
     * @param {boolean} [options.autoRange=true] - 是否自动计算 Y 轴范围（false
     *     则固定为 [0, 1]）
     * @param {Object} [options.layoutOverrides] - 额外覆盖的 Plotly layout 属性
     * @returns {void}
     */
    ns.createTrendChart = function (containerId, trendData, options) {
        if (!trendData || !trendData.length) return;

        options = options || {};
        var lineWidth = options.lineWidth !== undefined ? options.lineWidth : 2.5;
        var markerSize = options.markerSize !== undefined ? options.markerSize : 7;
        var autoRange = options.autoRange !== false;
        var xTitle = options.xTitle || "年份";
        var yTitle = options.yTitle || "热度值";

        // 构建 traces
        var traces = trendData.map(function (series, i) {
            return {
                x: series.x,
                y: series.y,
                mode: "lines+markers",
                name: series.keyword,
                line: { width: lineWidth, color: COLOR_PALETTE[i % COLOR_PALETTE.length] },
                marker: { size: markerSize },
                hovertemplate: series.keyword + "<br>%{x}: %{y:.3f}<extra></extra>",
            };
        });

        // 构建 layout（合并默认配置）
        var layout = Object.assign({}, BASE_LAYOUT, {
            xaxis: {
                title: xTitle,
                dtick: 1,
                gridcolor: "#f0f0f0",
            },
            yaxis: {
                title: yTitle,
                gridcolor: "#f0f0f0",
            },
            showlegend: true,
            legend: { x: 0.01, y: 0.99 },
        });

        // Y 轴范围
        if (autoRange) {
            var allY = trendData.reduce(function (acc, s) { return acc.concat(s.y); }, []);
            if (allY.length) {
                layout.yaxis.range = [0, Math.max(1, Math.ceil(Math.max.apply(null, allY) * 10) / 10)];
            }
        } else {
            layout.yaxis.range = [0, 1];
        }

        // 用户自定义覆盖
        if (options.layoutOverrides) {
            deepMerge(layout, options.layoutOverrides);
        }

        Plotly.newPlot(containerId, traces, layout, { responsive: true, displayModeBar: false });
    };

    // ═══════════════════════════════════════════
    // 饼图（学科分布等）
    // ═══════════════════════════════════════════

    /**
     * 创建环形饼图（如学科分布）。
     *
     * @param {string} containerId - 图表容器 DOM 元素 ID
     * @param {Object} data - 数据，格式：{ label: count, ... }
     * @param {Object} [options] - 可选配置
     * @param {number} [options.hole=0.35] - 环形空心大小（0 为实心饼图）
     * @param {string[]} [options.colors] - 颜色数组
     * @param {Object} [options.layoutOverrides] - 额外覆盖的 Plotly layout 属性
     * @returns {void}
     */
    ns.createCategoryPieChart = function (containerId, data, options) {
        var labels = Object.keys(data);
        var values = Object.values(data);
        if (!labels.length) return;

        options = options || {};
        var hole = options.hole !== undefined ? options.hole : 0.35;
        var colors = options.colors || COLOR_PALETTE;

        var trace = {
            type: "pie",
            labels: labels,
            values: values,
            hole: hole,
            marker: { colors: colors },
            textinfo: "label+percent",
            textposition: "outside",
        };

        var layout = Object.assign({}, BASE_LAYOUT, {
            margin: { l: 10, r: 10, t: 10, b: 10 },
            showlegend: true,
            legend: { x: 0.85, y: 0.5 },
        });

        if (options.layoutOverrides) {
            deepMerge(layout, options.layoutOverrides);
        }

        Plotly.newPlot(containerId, [trace], layout, { responsive: true, displayModeBar: false });
    };

    // ═══════════════════════════════════════════
    // 快捷数据获取
    // ═══════════════════════════════════════════

    /**
     * 从 /api/trend 获取指定关键词的趋势数据。
     *
     * @param {string[]} keywords - 关键词列表
     * @returns {Promise<Array>} trendData 数组
     */
    ns.fetchTrendData = async function (keywords) {
        var resp = await fetch("/api/trend", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ selected_keywords: keywords }),
        });
        var data = await resp.json();
        return data.trends || [];
    };

    /**
     * 获取热度排名 TOP N 的关键词，并返回其趋势数据。
     *
     * @param {number} [n=5] - 取前 N 个关键词
     * @returns {Promise<Array>} trendData 数组
     */
    ns.fetchTopKeywordsTrend = async function (n) {
        n = n || 5;
        var kwResp = await fetch("/api/top-keywords?n=" + n);
        var kwData = await kwResp.json();
        if (!kwData.top_keywords || !kwData.top_keywords.length) return [];
        var topKws = kwData.top_keywords.slice(0, n).map(function (k) { return k.keyword; });
        return ns.fetchTrendData(topKws);
    };

    // ═══════════════════════════════════════════
    // 内部工具
    // ═══════════════════════════════════════════

    /**
     * 浅层递归合并 b 到 a（仅处理普通对象）。
     */
    function deepMerge(target, source) {
        Object.keys(source).forEach(function (key) {
            var sv = source[key];
            var tv = target[key];
            if (sv !== null && typeof sv === "object" && !Array.isArray(sv) &&
                tv !== null && typeof tv === "object" && !Array.isArray(tv)) {
                deepMerge(tv, sv);
            } else {
                target[key] = sv;
            }
        });
    }

})(window.InnoCite);
