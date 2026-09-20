/**
 * InnoCite 关键词热度趋势页脚本
 * 负责关键词列表加载、热度排行、词云、已选标签管理、曲线绘制。
 */
(function () {
    "use strict";

    var allKeywords = [];
    var heatmapData = null;
    var selectedKeywords = {};  // {keyword: true}

    document.addEventListener("DOMContentLoaded", function () {
        console.log("[Trends] 页面加载完成，开始获取数据...");
        loadKeywordData();
        loadTopKeywords();
    });

    /* ── 显示加载错误 ── */
    function showError(containerId, msg) {
        var el = document.getElementById(containerId);
        if (el) {
            el.innerHTML = '<div class=\"text-center py-4 text-danger\">' +
                '<i class=\"bi bi-exclamation-triangle\" style=\"font-size:2rem;\"></i>' +
                '<p class=\"mt-2 small\">' + msg + '</p>' +
                '<button class=\"btn btn-sm btn-outline-secondary\" onclick=\"location.reload()\">重试</button>' +
                '</div>';
        }
    }

    /* ── 加载关键词数据 ── */
    async function loadKeywordData() {
        try {
            var resp = await fetch("/api/keywords");
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            var data = await resp.json();
            allKeywords = data.keywords || [];
            heatmapData = data.heatmap || {};

            console.log("[Trends] 关键词数据已加载:", allKeywords.length, "个关键词,", (data.years || []).length, "年");

            // 统计栏
            var kwCount = document.getElementById("statKwCount");
            if (kwCount) kwCount.textContent = allKeywords.length;
            var yrEl = document.getElementById("statYearRange");
            if (yrEl && data.years && data.years.length) {
                yrEl.textContent = data.years[0] + " - " + data.years[data.years.length - 1];
            }
        } catch (e) {
            console.error("[Trends] 加载关键词失败:", e);
            showError("trendChart", "关键词数据加载失败：" + e.message);
        }
    }

    /* ── 加载热度排名 + 词云 ── */
    async function loadTopKeywords() {
        try {
            var resp = await fetch("/api/top-keywords?n=20");
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            var data = await resp.json();
            if (!data.top_keywords || !data.top_keywords.length) {
                console.warn("[Trends] 无关键词数据");
                return;
            }
            console.log("[Trends] 排名数据已加载:", data.top_keywords.length, "条");

            var medals = ["🥇", "🥈", "🥉"];

            // 更新排名 badge
            var rc = document.getElementById("rankCount");
            if (rc) rc.textContent = "TOP " + Math.min(data.top_keywords.length, 20);

            // 最热词
            if (data.top_keywords.length > 0) {
                var topEl = document.getElementById("statTopKw");
                if (topEl) topEl.textContent = data.top_keywords[0].keyword;
            }

            // 排名列表
            var rankHtml = '<div class="list-group list-group-flush">';
            data.top_keywords.forEach(function (item, i) {
                var medal = i < 3 ? medals[i] : (i + 1) + ".";
                var isActive = selectedKeywords[item.keyword] ? " active" : "";
                rankHtml +=
                    '<a href="#" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center py-2 px-3' + isActive + '"' +
                    ' data-keyword="' + item.keyword.replace(/"/g, '&quot;') + '">' +
                    '<span class="small text-truncate" style="max-width:70%;">' + medal + " " + item.keyword + "</span>" +
                    '<span class="badge bg-primary rounded-pill flex-shrink-0">' + (item.avg_heat * 100).toFixed(1) + "%</span>" +
                    "</a>";
            });
            rankHtml += "</div>";
            var rankingEl = document.getElementById("topRanking");
            if (rankingEl) {
                rankingEl.innerHTML = rankHtml;
                // 排名点击事件委托
                rankingEl.addEventListener("click", function (e) {
                    var item = e.target.closest("[data-keyword]");
                    if (!item) return;
                    e.preventDefault();
                    var kw = item.getAttribute("data-keyword");
                    toggleKeyword(kw);
                });
            }

            // 词云渲染
            renderWordCloud(data.top_keywords);
        } catch (e) {
            console.error("[Trends] 加载排名失败:", e);
            showError("topRanking", "热度排名加载失败：" + e.message);
            showError("wordCloud", "词云加载失败");
        }
    }

    /* ── 切换关键词选中状态 ── */
    function toggleKeyword(kw) {
        if (selectedKeywords[kw]) {
            delete selectedKeywords[kw];
        } else {
            selectedKeywords[kw] = true;
        }
        updateSelectedUI();
    }

    /* ── 更新已选标签 + 按钮状态 + 排名字高亮 ── */
    function updateSelectedUI() {
        var tags = [];
        var count = 0;
        for (var kw in selectedKeywords) {
            if (selectedKeywords.hasOwnProperty(kw)) {
                tags.push(kw);
                count++;
            }
        }

        // 已选标签
        var tagsEl = document.getElementById("selectedTags");
        if (tagsEl) {
            tagsEl.innerHTML = tags.map(function (kw) {
                return '<span class="badge bg-primary bg-opacity-10 text-primary border border-primary border-opacity-25 d-inline-flex align-items-center gap-1 py-1 px-2" style="cursor:pointer;" onclick="InnoCite.removeKeyword(\'' + kw.replace(/'/g, "\\'") + '\')">' +
                    kw + '<i class="bi bi-x small"></i></span>';
            }).join("");
        }

        // 计数
        var cntEl = document.getElementById("selectedCount");
        if (cntEl) cntEl.textContent = count;

        // 按钮状态
        var btnPlot = document.getElementById("btnPlot");
        var btnClear = document.getElementById("btnClear");
        if (btnPlot) btnPlot.disabled = count === 0;
        if (btnClear) btnClear.disabled = count === 0;

        // 图表提示
        var hint = document.getElementById("chartHint");
        if (hint) {
            hint.textContent = count > 0 ? count + ' 个关键词已选，点击「绘制曲线」' : '选择下方关键词后点击「绘制曲线」';
        }

        // 排名字高亮
        var rankingEl = document.getElementById("topRanking");
        if (rankingEl) {
            var items = rankingEl.querySelectorAll("[data-keyword]");
            items.forEach(function (item) {
                var kw = item.getAttribute("data-keyword");
                item.classList.toggle("active", !!selectedKeywords[kw]);
            });
        }
    }

    /* ── 外部调用：移除单个关键词 ── */
    InnoCite.removeKeyword = function (kw) {
        delete selectedKeywords[kw];
        updateSelectedUI();
    };

    /* ── 清除选择 ── */
    window.clearSelection = function () {
        selectedKeywords = {};
        updateSelectedUI();
    };

    /* ── 绘制曲线 ── */
    window.plotTrends = async function () {
        var keywords = Object.keys(selectedKeywords);
        if (keywords.length === 0) return;
        try {
            var trendData = await InnoCite.fetchTrendData(keywords);
            if (trendData.length > 0) {
                InnoCite.createTrendChart("trendChart", trendData);
            }
        } catch (e) {
            console.error("绘制失败:", e);
        }
    };

    /* ── 刷新页面 ── */
    window.refreshData = function () {
        location.reload();
    };

    /* ── 词云 ── */
    function renderWordCloud(keywords) {
        var cloud = document.getElementById("wordCloud");
        if (!cloud || !keywords || !keywords.length) return;
        if (keywords.length < 3) {
            cloud.innerHTML = '<span class="text-muted small">数据量不足</span>';
            return;
        }
        var maxHeat = keywords[0].avg_heat;
        var minHeat = keywords[keywords.length - 1].avg_heat;
        var range = maxHeat - minHeat || 1;
        var top30 = keywords.slice(0, 30);
        var html = "";
        var activeSet = selectedKeywords;  // 引用当前选中状态

        top30.forEach(function (item) {
            var norm = (item.avg_heat - minHeat) / range;
            var size = 0.7 + norm * 2.0;
            var opacity = 0.4 + norm * 0.6;
            var isActive = activeSet[item.keyword] ? " fw-bold" : "";
            html += '<span class="word' + isActive + '" style="font-size:' + size.toFixed(2) +
                'rem;opacity:' + opacity.toFixed(2) +
                ';" onclick="InnoCite.cloudClick(\'' +
                item.keyword.replace(/'/g, "\\'") + '\')" title="' +
                item.keyword + ' (' + (item.avg_heat * 100).toFixed(1) + '%)">' +
                item.keyword + "</span>";
        });
        cloud.innerHTML = html;
    }

    /* ── 词云点击 ── */
    InnoCite.cloudClick = function (kw) {
        toggleKeyword(kw);
        // 词云重新渲染以高亮
        var resp = fetch("/api/top-keywords?n=30")
            .then(function (r) { return r.json(); })
            .then(function (d) { renderWordCloud(d.top_keywords); });
    };

})();

// ═══════════════════════════════════════════
// 河流图
// ═══════════════════════════════════════════

function loadRiverChart() {
    fetch('/api/trend/river-chart?top_n=6')
        .then(r => r.json())
        .then(d => {
            if (!d.success || !d.series || !d.series.length) {
                document.getElementById('riverChart').innerHTML =
                    '<div class="text-center text-muted py-5">数据不足，无法生成河流图</div>';
                return;
            }
            const traces = d.series.map((s, i) => ({
                x: s.x,
                y: s.y,
                name: s.keyword,
                type: 'scatter',
                mode: 'lines',
                stackgroup: 'one',
                groupnorm: 'percent',
                line: { width: 0.5 },
                fill: 'tonexty',
            }));
            const layout = {
                title: '关键词热度占比演变',
                yaxis: { title: '占比', tickformat: '.0%' },
                xaxis: { title: '年份' },
                margin: { l: 50, r: 10, t: 40, b: 40 },
                hovermode: 'x unified',
                showlegend: true,
                legend: { x: 1.02, y: 1 },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
            };
            Plotly.newPlot('riverChart', traces, layout, { responsive: true });
        });
}

// 监听河流图标签页切换
document.addEventListener('DOMContentLoaded', () => {
    const riverBtn = document.querySelector('[data-bs-target="#riverTab"]');
    if (riverBtn) {
        riverBtn.addEventListener('shown.bs.tab', () => {
            if (!document.getElementById('riverChart').hasChildNodes()) {
                loadRiverChart();
            }
        });
    }
    // 首次加载（如果默认激活）
    if (document.getElementById('riverTab') && document.getElementById('riverTab').classList.contains('active')) {
        setTimeout(loadRiverChart, 500);
    }
});

// ═══════════════════════════════════════════
// 方法迁移路径
// ═══════════════════════════════════════════

function loadMigration() {
    const kw = document.getElementById('migrationKw').value.trim();
    if (!kw) { alert('请输入方法关键词'); return; }

    const container = document.getElementById('migrationResult');
    container.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div> 分析中...</div>';

    fetch(`/api/trend/migration?keyword=${encodeURIComponent(kw)}`)
        .then(r => r.json())
        .then(d => {
            if (!d.success || !d.migration || !d.migration.length) {
                container.innerHTML =
                    `<div class="alert alert-warning">未找到与「${kw}」相关的方法在论文库中的跨学科数据。请尝试其他关键词。</div>`;
                return;
            }

            const colors = { 'cs.CV': '#0f3460', 'cs.CL': '#e94560', 'cs.AI': '#533483', 'cs.LG': '#00b4d8' };

            let html = `<h6>「${kw}」跨学科传播路径 <span class="badge bg-secondary">共 ${d.total_papers} 篇</span></h6>`;
            html += '<div class="table-responsive"><table class="table table-sm"><thead><tr>';
            html += '<th>顺序</th><th>学科</th><th>首次出现</th><th>论文数</th><th>代表论文</th>';
            html += '</tr></thead><tbody>';

            d.migration.forEach((m, i) => {
                const color = colors[m.category] || '#6c757d';
                html += `<tr>
                    <td>${i + 1}</td>
                    <td><span class="badge" style="background:${color}">${m.category}</span></td>
                    <td>${m.first_year || '?'}</td>
                    <td>${m.paper_count} 篇</td>
                    <td class="small">${m.sample_title || '—'} (${m.sample_year || ''})</td>
                </tr>`;
            });
            html += '</tbody></table></div>';

            // 简易迁移箭头图
            if (d.migration.length > 1) {
                html += '<div class="d-flex flex-wrap align-items-center gap-2 mt-3 small">';
                html += '<strong class="text-muted">迁移路径 → </strong>';
                d.migration.forEach((m, i) => {
                    const color = colors[m.category] || '#6c757d';
                    if (i > 0) html += '<span class="text-muted">→</span>';
                    html += `<span class="badge" style="background:${color}">${m.category} (${m.first_year})</span>`;
                });
                html += '</div>';
            }

            container.innerHTML = html;
        })
        .catch(() => {
            container.innerHTML = '<div class="alert alert-danger">加载失败</div>';
        });
}
