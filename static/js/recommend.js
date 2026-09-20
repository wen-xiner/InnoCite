/**
 * InnoCite 跨学科推荐页脚本
 * 负责论文搜索筛选、阈值调节、推荐结果加载。
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var paperSearch = document.getElementById("paperSearch");
        var threshold = document.getElementById("threshold");

        // 论文搜索筛选
        if (paperSearch) {
            paperSearch.addEventListener("input", function () {
                var query = this.value.toLowerCase();
                var select = document.getElementById("paperSelect");
                if (!select) return;
                for (var i = 0; i < select.options.length; i++) {
                    select.options[i].style.display =
                        select.options[i].textContent.toLowerCase().indexOf(query) !== -1 ? "" : "none";
                }
            });
        }

        // 阈值滑块显示
        if (threshold) {
            threshold.addEventListener("input", function () {
                var label = document.getElementById("thresholdLabel");
                if (label) label.textContent = parseFloat(this.value).toFixed(2);
            });
        }
    });

    /* ── 获取推荐 ── */
    window.getRecommendations = async function () {
        var paperId = document.getElementById("paperSelect").value;
        var topN = document.getElementById("topN").value;
        if (!paperId) {
            alert("请选择一篇论文");
            return;
        }

        var resultsDiv = document.getElementById("recommendResults");
        if (!resultsDiv) return;

        // 骨架屏
        var skeleton = "";
        for (var i = 0; i < 3; i++) {
            skeleton +=
                '<div class="skeleton-rec-card">' +
                '<div class="skeleton skeleton-text"></div>' +
                '<div class="skeleton skeleton-text"></div>' +
                '<div class="skeleton skeleton-text"></div>' +
                "</div>";
        }
        resultsDiv.innerHTML = skeleton;

        try {
            var resp = await fetch(
                "/api/recommend?paper_id=" + paperId + "&top_n=" + topN + "&force_refresh=1"
            );
            var data = await resp.json();

            if (!data.success) {
                resultsDiv.innerHTML = '<div class="alert alert-danger">' + data.message + "</div>";
                return;
            }

            // 源论文摘要 — 显示在左侧 sticky 栏内
            var sp = data.source_paper;
            var srcCard = document.getElementById("sourcePaperCard");
            if (srcCard) srcCard.style.display = "";
            var srcTitle = document.getElementById("sourceTitle");
            if (srcTitle) srcTitle.textContent = sp.title;
            var srcMeta = document.getElementById("sourceMeta");
            if (srcMeta) {
                srcMeta.textContent =
                    (sp.authors ? sp.authors.join("; ") : "未知") +
                    " · " + (sp.year || "N/A") +
                    " · " + (sp.category || "N/A");
            }
            var srcAbstract = document.getElementById("sourceAbstract");
            if (srcAbstract) {
                srcAbstract.textContent = (sp.abstract || "暂无摘要").substring(0, 250) + "...";
            }

            // 推荐结果
            if (data.recommendations && data.recommendations.length > 0) {
                var html = '<h6 class="mb-3">推荐结果（共 ' + data.recommendations.length + " 条）</h6>";
                data.recommendations.forEach(function (rec, i) {
                    var simPercent = (rec.similarity * 100).toFixed(1);
                    var simColor = rec.similarity >= 0.5 ? '#10b981' :
                                   rec.similarity >= 0.3 ? '#f59e0b' : '#ef4444';
                    html +=
                        '<div class="card mb-3"><div class="card-body">' +
                        '<div class="d-flex justify-content-between align-items-start mb-2">' +
                        '<div style="flex:1;min-width:0;"><h6 class="card-title mb-1 text-truncate">' + rec.target_title + "</h6>" +
                        '<p class="small text-muted mb-0">' +
                        (rec.target_authors ? rec.target_authors.join("; ") : "未知") +
                        " · " + (rec.target_year || "N/A") + "</p></div>" +
                        '<div class="text-end ms-2 flex-shrink-0">' +
                        '<span class="fw-bold" style="font-size:1.1rem;color:' + simColor + ';">' + simPercent + "%</span>" +
                        "</div>" +
                        "</div>" +
                        '<div class="heat-bar mb-2">' +
                        '<div class="heat-bar-fill" style="width:' + simPercent + '%;background:' + simColor + ';"></div>' +
                        "</div>" +
                        '<div class="d-flex gap-2 mb-2">' +
                        '<span class="badge bg-info text-dark">' + (rec.target_category || "N/A") + "</span>" +
                        '<span class="badge bg-light text-dark">推荐 #' + (i + 1) + "</span>" +
                        "</div>" +
                        '<div class="alert alert-light mb-0">' +
                        '<i class="bi bi-chat-left-quote"></i> ' + rec.reason + "</div>" +
                        "</div></div>";
                });
                resultsDiv.innerHTML = html;
            } else {
                resultsDiv.innerHTML =
                    '<div class="alert alert-warning">' +
                    '<i class="bi bi-exclamation-triangle"></i> ' +
                    "未找到符合条件的跨学科推荐。请尝试选择其他论文或降低相似度阈值。</div>";
            }
        } catch (e) {
            resultsDiv.innerHTML = '<div class="alert alert-danger">获取推荐失败: ' + e.message + "</div>";
        }
    };
})();
