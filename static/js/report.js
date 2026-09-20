/**
 * InnoCite 综合报告页脚本
 * 负责统计卡片、图表、创新点表格、推荐示例的加载。
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        buildSkeletonTableRows("innoTableBody", 5, 4);
        loadStats();
        loadReportCharts();
        loadInnovations();
        loadRecommendations();
    });

    /* ── 表格骨架屏 ── */
    function buildSkeletonTableRows(tbodyId, rowCount, colCount) {
        var tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        var html = "";
        for (var r = 0; r < rowCount; r++) {
            html += '<div class="skeleton-table-row" style="margin:0;border-bottom:1px solid #eee;">';
            for (var c = 0; c < colCount; c++) {
                html += '<div class="skeleton skeleton-cell" style="height:14px;flex:1;"></div>';
            }
            html += "</div>";
        }
        tbody.innerHTML = html;
    }

    /* ── 统计卡片 ── */
    async function loadStats() {
        var container = document.getElementById("statsCards");
        if (!container) return;
        try {
            var resp = await fetch("/api/stats");
            var data = await resp.json();
            var catCount = Object.keys(data.categories || {}).length;
            var confPct = ((data.avg_confidence || 0) * 100).toFixed(0);
            container.innerHTML =
                '<div class="row mb-4">' +
                '<div class="col-md-3"><div class="card border-0 bg-primary text-white"><div class="card-body text-center">' +
                '<i class="bi bi-journals" style="font-size:2rem;"></i><h2 class="mt-2">' + data.paper_count + '</h2><p class="mb-0 small">论文总数</p>' +
                '</div></div></div>' +
                '<div class="col-md-3"><div class="card border-0 bg-success text-white"><div class="card-body text-center">' +
                '<i class="bi bi-calendar-range" style="font-size:2rem;"></i><h2 class="mt-2">' + data.year_range + '</h2><p class="mb-0 small">年份范围</p>' +
                '</div></div></div>' +
                '<div class="col-md-3"><div class="card border-0 bg-info text-white"><div class="card-body text-center">' +
                '<i class="bi bi-diagram-3" style="font-size:2rem;"></i><h2 class="mt-2">' + catCount + '</h2><p class="mb-0 small">学科数量</p>' +
                '</div></div></div>' +
                '<div class="col-md-3"><div class="card border-0 bg-warning text-dark"><div class="card-body text-center">' +
                '<i class="bi bi-check-circle" style="font-size:2rem;"></i><h2 class="mt-2" style="color:#333;">' + confPct + '%</h2><p class="mb-0 small">平均置信度</p>' +
                '</div></div></div></div>';
        } catch (e) {
            console.error("加载统计失败:", e);
        }
    }

    /* ── 图表 ── */
    async function loadReportCharts() {
        try {
            var trendData = await InnoCite.fetchTopKeywordsTrend(5);
            if (trendData.length > 0) {
                InnoCite.createTrendChart("reportTrendChart", trendData, {
                    autoRange: false,
                    lineWidth: 2,
                    markerSize: 6,
                });
            }
            var statsResp = await fetch("/api/stats");
            var statsData = await statsResp.json();
            if (statsData.categories && Object.keys(statsData.categories).length > 0) {
                InnoCite.createCategoryPieChart("reportPieChart", statsData.categories);
            }
        } catch (e) {
            console.error("加载图表失败:", e);
        }
    }

    /* ── 创新点表格 ── */
    async function loadInnovations() {
        var tbody = document.getElementById("innoTableBody");
        if (!tbody) return;
        try {
            var resp = await fetch("/api/innovations?page=1&per_page=10");
            var data = await resp.json();
            var html = "";
            const items = data.data || [];  // api_paginated 将列表包装在 data 字段
            if (items.length > 0) {
                items.forEach(function (inv) {
                    var confClass = inv.confidence >= 0.5 ? "bg-success" : "bg-warning";
                    var checkIcon = inv.is_verified
                        ? '<i class="bi bi-check-circle text-success"></i>'
                        : '<i class="bi bi-dash-circle text-muted"></i>';
                    html +=
                        "<tr>" +
                        '<td class="small">' + (inv.paper_title || "").substring(0, 50) + "</td>" +
                        "<td>" + (inv.paper_year || "-") + "</td>" +
                        '<td><span class="badge ' + confClass + '">' + (inv.confidence * 100).toFixed(0) + "%</span></td>" +
                        "<td>" + checkIcon + "</td>" +
                        "</tr>";
                });
            } else {
                html = '<tr><td colspan="4" class="text-center text-muted py-3">暂无创新点数据</td></tr>';
            }
            tbody.innerHTML = html;
        } catch (e) {
            console.error("加载创新点失败:", e);
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-danger py-3">加载失败</td></tr>';
        }
    }

    /* ── 推荐示例 ── */
    async function loadRecommendations() {
        var container = document.getElementById("reportRecommendations");
        if (!container) return;
        try {
            var resp = await fetch("/api/recommend-sample?top_n=3");
            var data = await resp.json();
            var html = "";
            if (data.recommendations && data.recommendations.length > 0) {
                data.recommendations.forEach(function (rec) {
                    html +=
                        '<div class="mb-2 p-3 border rounded">' +
                        '<strong class="small">' + rec.target_title + "</strong>" +
                        '<span class="badge bg-info text-dark ms-2">' + (rec.target_category || "") + "</span>" +
                        '<span class="badge bg-secondary ms-1">' + (rec.similarity * 100).toFixed(1) + "%</span>" +
                        '<p class="small text-muted mt-1 mb-0">' + rec.reason + "</p>" +
                        "</div>";
                });
            } else {
                html = '<p class="text-muted">暂无推荐数据</p>';
            }
            container.innerHTML = html;
        } catch (e) {
            console.error("加载推荐失败:", e);
            container.innerHTML = '<p class="text-danger">加载推荐失败</p>';
        }
    }

    /* ── PDF 导出 ── */
    window.exportPDF = async function () {
        var btn = document.getElementById("exportBtn");
        var overlay = document.getElementById("loadingOverlay");
        if (!btn || !overlay) return;

        btn.disabled = true;
        overlay.style.display = "";

        try {
            var resp = await fetch("/api/export_pdf", { method: "POST" });
            if (resp.ok) {
                var blob = await resp.blob();
                var url = URL.createObjectURL(blob);
                var a = document.createElement("a");
                a.href = url;
                a.download = "InnoCite_Report_" + new Date().toISOString().slice(0, 10) + ".pdf";
                a.click();
                URL.revokeObjectURL(url);
            } else {
                var data = await resp.json();
                alert("PDF导出失败: " + (data.message || "未知错误"));
            }
        } catch (e) {
            alert("导出失败: " + e.message);
        } finally {
            btn.disabled = false;
            overlay.style.display = "none";
        }
    };
})();

// ═══════════════════════════════════════════
// 文献综述生成
// ═══════════════════════════════════════════

function generateReview() {
    const topic = document.getElementById('reviewTopic').value.trim();
    if (!topic) { alert('请输入综述主题'); return; }

    const output = document.getElementById('reviewOutput');
    output.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div> 正在生成综述，请稍候...</div>';

    fetch('/api/review/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken(),
        },
        body: JSON.stringify({ topic: topic, max_papers: 15 }),
        credentials: 'same-origin',
    })
    .then(r => r.json())
    .then(d => {
        if (!d.success) {
            output.innerHTML = `<div class="alert alert-warning">${d.message || '生成失败'}</div>`;
            return;
        }
        if (!d.success || !d.review) {
            output.innerHTML = `<div class="alert alert-info">${d.message || '无相关数据'}</div>`;
            return;
        }

        // Markdown 简单渲染
        let html = d.review
            .replace(/^### (.+)$/gm, '<h5>$1</h5>')
            .replace(/^## (.+)$/gm, '<h4>$1</h4>')
            .replace(/^# (.+)$/gm, '<h3>$1</h3>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');

        html = '<p>' + html + '</p>';
        html = html.replace(/<li>/g, '<ul><li>').replace(/<\/li>(?![\s\S]*?<li>)/g, '</li></ul>');

        const sourceBadge = d.source === 'llm'
            ? '<span class="badge bg-success">AI 生成</span>'
            : '<span class="badge bg-secondary">模板生成</span>';

        output.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-2">
                <span><strong>${escHtml(d.topic)}</strong> — 共 ${d.paper_count} 篇论文</span>
                ${sourceBadge}
            </div>
            <hr>
            <div style="line-height:1.8;">${html}</div>`;
    })
    .catch(e => {
        output.innerHTML = `<div class="alert alert-danger">请求失败: ${e.message}</div>`;
    });
}

function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
