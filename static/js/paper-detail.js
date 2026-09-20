/**
 * InnoCite 论文详情页脚本
 * 负责加载跨学科推荐 + 快速操作悬浮栏。
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var recommendCard = document.getElementById("recommendCard");
        if (recommendCard) {
            var paperId = recommendCard.getAttribute("data-paper-id");
            if (paperId) loadRecommendations(parseInt(paperId, 10));
        }

        // 快速操作悬浮栏：滚动超过面包屑区时滑入
        var actionBar = document.getElementById("quickActionBar");
        if (actionBar) {
            var ticking = false;
            window.addEventListener("scroll", function () {
                if (!ticking) {
                    requestAnimationFrame(function () {
                        var show = window.scrollY > 120;
                        actionBar.classList.toggle("visible", show);
                        ticking = false;
                    });
                    ticking = true;
                }
            }, { passive: true });
        }
    });

    async function loadRecommendations(paperId) {
        var resultsEl = document.getElementById("recResults");
        var loadingEl = document.getElementById("recLoading");
        if (!resultsEl) return;

        try {
            var resp = await fetch("/api/recommend?paper_id=" + paperId + "&top_n=3");
            var data = await resp.json();
            if (loadingEl) loadingEl.style.display = "none";

            if (data.recommendations && data.recommendations.length > 0) {
                var html = "";
                data.recommendations.forEach(function (rec) {
                    var simPct = (rec.similarity * 100).toFixed(1);
                    var simColor = rec.similarity >= 0.5 ? '#10b981' :
                                   rec.similarity >= 0.3 ? '#f59e0b' : '#ef4444';
                    html +=
                        '<div class="mb-3 p-2 border rounded">' +
                        '<div class="small fw-bold">' + rec.target_title + "</div>" +
                        '<div class="small text-muted">' +
                        (rec.target_category || "") + " · " +
                        (rec.target_year || "") + " · 相似度 " +
                        simPct + "%</div>" +
                        '<div class="heat-bar mb-1"><div class="heat-bar-fill" style="width:' + simPct + '%;background:' + simColor + ';"></div></div>' +
                        '<div class="small mt-1">' + rec.reason + "</div>" +
                        "</div>";
                });
                resultsEl.innerHTML = html;
            } else {
                resultsEl.innerHTML = '<p class="text-muted text-center">暂无跨学科推荐</p>';
            }
        } catch (e) {
            if (loadingEl) loadingEl.style.display = "none";
            resultsEl.innerHTML = '<p class="text-danger">获取推荐失败</p>';
        }
    }
})();
