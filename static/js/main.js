/**
 * InnoCite 前端通用脚本
 */

// ═══════════════════════════════════════════
// 全局进度条 — 页面切换时顶部 3px 细线动画
// ═══════════════════════════════════════════
(function () {
    var bar = document.getElementById('globalProgress');
    if (!bar) return;
    var width = 0;
    var timer = setInterval(function () {
        width += Math.random() * 25;
        if (width > 85) { width = 85; clearInterval(timer); }
        bar.style.width = width + '%';
    }, 200);
    window.addEventListener('load', function () {
        bar.style.width = '100%';
        setTimeout(function () { bar.style.width = '0'; }, 400);
    });
    // 链接点击时也触发
    document.addEventListener('click', function (e) {
        var link = e.target.closest('a[href]:not([target]):not([download]):not([onclick])');
        if (link && link.href && link.href.startsWith(window.location.origin)) {
            bar.style.width = '0';
            bar.style.transition = 'none';
            setTimeout(function () {
                bar.style.transition = 'width .4s ease-out';
                bar.style.width = '60%';
            }, 50);
        }
    });
})();

// ═══════════════════════════════════════════
// CSRF 保护 — 全局 fetch 包装器
// 自动为所有同源 POST/PUT/DELETE/PATCH 请求注入 CSRF token。
// Flask-WTF CSRFProtect 会在首次页面加载时写入名为 csrf_token 的 Cookie，
// 前端读取该 Cookie 并通过 X-CSRFToken 请求头发送回服务器。
// ═══════════════════════════════════════════

(function () {
    /**
     * 读取 CSRF token。
     * Flask-WTF 将 token 存储在服务端 session 中，并通过
     * <meta name="csrf-token"> 输出到页面。JS 读取后通过
     * X-CSRFToken 请求头发送回服务器进行校验。
     */
    function getCSRFToken() {
        // 方式1：从 <meta> 标签读取（由 base.html 中的 csrf_token() 渲染）
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) {
            return meta.getAttribute('content');
        }
        // 方式2：回退到独立的 csrf_token Cookie（部分部署配置会写入）
        var value = '; ' + document.cookie;
        var parts = value.split('; csrf_token=');
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return null;
    }

    var _originalFetch = window.fetch;
    window.fetch = function (url, options) {
        options = options || {};
        var method = (options.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'DELETE', 'PATCH'].indexOf(method) !== -1) {
            var token = getCSRFToken();
            if (token) {
                options.headers = options.headers || {};
                // 仅在未显式设置时注入（避免覆盖用户自定义头）
                if (!options.headers['X-CSRFToken']) {
                    options.headers['X-CSRFToken'] = token;
                }
            }
        }
        return _originalFetch(url, options);
    };
})();

// ═══════════════════════════════════════════
// 暗色模式
// ═══════════════════════════════════════════

(function () {
    var saved = localStorage.getItem('innocite-theme');
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (saved === 'dark' || (!saved && prefersDark)) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }

    document.addEventListener('DOMContentLoaded', function () {
        var btn = document.getElementById('themeToggle');
        if (!btn) return;
        btn.addEventListener('click', function () {
            var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            if (isDark) {
                document.documentElement.removeAttribute('data-theme');
                localStorage.setItem('innocite-theme', 'light');
                btn.innerHTML = '<i class="bi bi-moon-stars-fill"></i>';
            } else {
                document.documentElement.setAttribute('data-theme', 'dark');
                localStorage.setItem('innocite-theme', 'dark');
                btn.innerHTML = '<i class="bi bi-sun-fill"></i>';
            }
            updateIcon();
        });
        updateIcon();
        function updateIcon() {
            var dark = document.documentElement.getAttribute('data-theme') === 'dark';
            btn.innerHTML = dark ? '<i class="bi bi-sun-fill"></i>' : '<i class="bi bi-moon-stars-fill"></i>';
        }
    });
})();

// ═══════════════════════════════════════════
// 论文导入
// ═══════════════════════════════════════════

async function importArxivId(event) {
    event.preventDefault();
    const form = event.target;
    const input = form.querySelector('input');
    const resultDiv = document.getElementById('arxivIdResult');
    const arxivId = input.value.trim();

    if (!arxivId) return;

    resultDiv.innerHTML = `<div class="spinner-border spinner-border-sm"></div> 正在导入...`;

    try {
        const resp = await fetch('/import/arxiv-id', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ arxiv_id: arxivId }),
        });
        const data = await resp.json();

        if (data.success) {
            resultDiv.innerHTML = `<div class="alert alert-success">${data.message}</div>`;
            input.value = '';
            setTimeout(() => location.reload(), 1500);
        } else {
            resultDiv.innerHTML = `<div class="alert alert-danger">${data.message}</div>`;
        }
    } catch (e) {
        resultDiv.innerHTML = `<div class="alert alert-danger">请求失败: ${e.message}</div>`;
    }
}

async function importArxivSearch(event) {
    event.preventDefault();
    const form = event.target;
    const inputs = form.querySelectorAll('input');
    const resultDiv = document.getElementById('arxivSearchResult');
    const progressDiv = document.getElementById('arxivSearchProgress');
    const progressBar = progressDiv ? progressDiv.querySelector('.progress-bar') : null;
    const statusText = progressDiv ? progressDiv.querySelector('.status-text') : null;
    const query = inputs[0].value.trim();
    const yearFrom = inputs[1].value ? parseInt(inputs[1].value) : null;
    const yearTo = inputs[2].value ? parseInt(inputs[2].value) : null;
    const maxResults = parseInt(inputs[3].value) || 20;

    if (!query) return;

    // 显示进度条
    if (progressDiv) {
        progressDiv.classList.add('active');
        progressBar.style.width = '0%';
        statusText.textContent = '正在连接 arXiv API…';
    }
    // 模拟渐进动画（实际进度不可知，用假进度提升等待体验）
    var fakeProgress = 0;
    var progressTimer = setInterval(function () {
        fakeProgress += Math.random() * 15;
        if (fakeProgress > 85) { fakeProgress = 85; clearInterval(progressTimer); }
        if (progressBar) progressBar.style.width = fakeProgress + '%';
        if (statusText && fakeProgress > 40) statusText.textContent = '正在解析论文元数据…';
    }, 600);

    try {
        const resp = await fetch('/import/arxiv-search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query, year_from: yearFrom, year_to: yearTo, max_results: maxResults,
            }),
        });
        const data = await resp.json();

        // 完成进度条
        clearInterval(progressTimer);
        if (progressBar) progressBar.style.width = '100%';
        if (statusText) statusText.textContent = data.success ? '导入完成！' : '导入失败';
        setTimeout(function () {
            if (progressDiv) progressDiv.classList.remove('active');
        }, 800);

        if (data.success) {
            resultDiv.innerHTML = `<div class="alert alert-success">${data.message}</div>`;
            setTimeout(() => location.reload(), 2000);
        } else {
            resultDiv.innerHTML = `<div class="alert alert-danger">${data.message}</div>`;
        }
    } catch (e) {
        clearInterval(progressTimer);
        if (progressBar) progressBar.style.width = '100%';
        if (statusText) statusText.textContent = '连接失败';
        if (progressDiv) progressDiv.classList.remove('active');
        resultDiv.innerHTML = `<div class="alert alert-danger">请求失败: ${e.message}</div>`;
    }
}

async function importCSV(event) {
    event.preventDefault();
    const form = event.target;
    const fileInput = form.querySelector('input[type="file"]');
    const resultDiv = document.getElementById('csvResult');

    if (!fileInput.files[0]) {
        resultDiv.innerHTML = '<div class="alert alert-warning">请选择CSV文件</div>';
        return;
    }

    resultDiv.innerHTML = `<div class="spinner-border spinner-border-sm"></div> 正在导入...`;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const resp = await fetch('/import/csv', { method: 'POST', body: formData });
        const data = await resp.json();

        if (data.success) {
            resultDiv.innerHTML = `<div class="alert alert-success">${data.message}</div>`;
            setTimeout(() => location.reload(), 1500);
        } else {
            resultDiv.innerHTML = `<div class="alert alert-danger">${data.message}</div>`;
        }
    } catch (e) {
        resultDiv.innerHTML = `<div class="alert alert-danger">请求失败: ${e.message}</div>`;
    }
}

async function importENW(event) {
    event.preventDefault();
    const form = event.target;
    const fileInput = form.querySelector('input[type="file"]');
    const resultDiv = document.getElementById('enwResult');

    if (!fileInput.files[0]) {
        resultDiv.innerHTML = '<div class="alert alert-warning">请选择 .enw 文件</div>';
        return;
    }

    resultDiv.innerHTML = '<div class="spinner-border spinner-border-sm"></div> 正在解析 EndNote 文件...';

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const resp = await fetch('/import/enw', { method: 'POST', body: formData });
        const data = await resp.json();

        if (data.success) {
            resultDiv.innerHTML = '<div class="alert alert-success">' + data.message + '</div>';
            setTimeout(function () { location.reload(); }, 1500);
        } else {
            resultDiv.innerHTML = '<div class="alert alert-danger">' + data.message + '</div>';
        }
    } catch (e) {
        resultDiv.innerHTML = '<div class="alert alert-danger">请求失败: ' + e.message + '</div>';
    }
}

async function importPDF(event) {
    event.preventDefault();
    const form = event.target;
    const fileInput = form.querySelector('input[type="file"]');
    const resultDiv = document.getElementById('pdfResult');

    if (!fileInput.files[0]) {
        resultDiv.innerHTML = '<div class="alert alert-warning">请选择PDF文件</div>';
        return;
    }

    resultDiv.innerHTML = `<div class="spinner-border spinner-border-sm"></div> 正在解析PDF...`;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const resp = await fetch('/import/pdf', { method: 'POST', body: formData });
        const data = await resp.json();

        if (data.success) {
            resultDiv.innerHTML = `
                <div class="alert alert-success">
                    ${data.message}<br>
                    ${data.id ? `<a href="/papers/${data.id}">查看详情 →</a>` : ''}
                </div>`;
            setTimeout(() => location.reload(), 1500);
        } else {
            resultDiv.innerHTML = `
                <div class="alert alert-warning">
                    ${data.message}
                    <button class="btn btn-sm btn-outline-warning mt-2" data-bs-toggle="modal" data-bs-target="#manualEditModal">
                        手动填写
                    </button>
                </div>`;
        }
    } catch (e) {
        resultDiv.innerHTML = `<div class="alert alert-danger">请求失败: ${e.message}</div>`;
    }
}


// ═══════════════════════════════════════════
// 事件委托（替代内联 onclick）
// ═══════════════════════════════════════════

document.addEventListener('click', function (event) {
    // 编辑创新点按钮
    var editBtn = event.target.closest('.edit-innovation-btn');
    if (editBtn) {
        var paperId = editBtn.getAttribute('data-paper-id');
        if (paperId) editInnovation(parseInt(paperId, 10));
        return;
    }

    // 删除论文按钮
    var deleteBtn = event.target.closest('.delete-paper-btn');
    if (deleteBtn) {
        var paperId = deleteBtn.getAttribute('data-paper-id');
        var paperTitle = deleteBtn.getAttribute('data-paper-title') || '';
        if (paperId) confirmDeletePaper(parseInt(paperId, 10), paperTitle);
        return;
    }
});

// ═══════════════════════════════════════════
// 创新点编辑
// ═══════════════════════════════════════════

async function editInnovation(paperId) {
    try {
        const resp = await fetch(`/papers/${paperId}/innovation`);
        const data = await resp.json();

        document.getElementById('innoPaperId').value = paperId;
        document.getElementById('innoProblem').value = data.problem === '待补充' ? '' : data.problem;
        document.getElementById('innoMethod').value = data.method === '待补充' ? '' : data.method;
        document.getElementById('innoEffect').value = data.effect === '待补充' ? '' : data.effect;
        updateInnovationPreview();

        const modal = new bootstrap.Modal(document.getElementById('innovationModal'));
        modal.show();
    } catch (e) {
        console.error('获取创新点失败:', e);
        alert('获取创新点失败');
    }
}

function updateInnovationPreview() {
    const problem = document.getElementById('innoProblem').value || '待补充';
    const method = document.getElementById('innoMethod').value || '待补充';
    const effect = document.getElementById('innoEffect').value || '待补充';

    let preview = '';
    if (problem !== '待补充') preview += `<strong>【问题】</strong> ${problem}<br>`;
    if (method !== '待补充') preview += `<strong>【方法】</strong> ${method}<br>`;
    if (effect !== '待补充') preview += `<strong>【效果】</strong> ${effect}`;
    if (!preview) preview = '（请至少填写一个字段）';

    document.getElementById('innoPreview').innerHTML = preview;
}

// 监听输入更新预览
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('innovationModal');
    if (modal) {
        modal.addEventListener('shown.bs.modal', () => {
            ['innoProblem', 'innoMethod', 'innoEffect'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.addEventListener('input', updateInnovationPreview);
            });
        });
    }
});

async function saveInnovation(event) {
    event.preventDefault();
    const paperId = document.getElementById('innoPaperId').value;
    const problem = document.getElementById('innoProblem').value;
    const method = document.getElementById('innoMethod').value;
    const effect = document.getElementById('innoEffect').value;

    try {
        const resp = await fetch(`/papers/${paperId}/innovation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                problem: problem || '待补充',
                method: method || '待补充',
                effect: effect || '待补充',
                is_verified: true,
            }),
        });
        const data = await resp.json();

        if (data.success) {
            const modal = bootstrap.Modal.getInstance(document.getElementById('innovationModal'));
            modal.hide();
            location.reload();
        } else {
            alert('保存失败: ' + data.message);
        }
    } catch (e) {
        console.error('保存创新点失败:', e);
        alert('保存失败');
    }
}


// ═══════════════════════════════════════════
// 数据导出
// ═══════════════════════════════════════════

/**
 * 导出论文数据（CSV 或 JSON），自动带入当前搜索/筛选条件。
 * @param {string} format - "csv" 或 "json"
 */
function exportData(format) {
    var params = new URLSearchParams(window.location.search);
    var exportParams = new URLSearchParams();

    // 带入当前搜索和筛选条件
    var q = params.get('q');
    var category = params.get('category');
    if (q) exportParams.set('q', q);
    if (category) exportParams.set('category', category);

    var queryString = exportParams.toString();
    var url = '/api/export/' + format;
    if (queryString) url += '?' + queryString;

    // 触发下载
    var a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

/**
 * 确认并执行删除论文。
 * @param {number} paperId - 论文 ID
 * @param {string} paperTitle - 论文标题（用于确认提示）
 */
// ═══════════════════════════════════════════
// 首页仪表盘 — 数字增长动画
// ═══════════════════════════════════════════

(function () {
    if (window.location.pathname !== '/') return;

    /**
     * 数字增长动画: 从 0 跃动增长到目标值。
     * 采用 setInterval 保证时序可靠、动画始终可见。
     */
    function animateNumber(el, target, suffix) {
        if (!el || isNaN(target) || target <= 0) return;
        suffix = suffix || '';
        var frames = 35;                            // 固定 35 帧，无论目标值大小
        var step = target / frames;                 // 每帧增量（可为小数）
        var current = 0;
        var count = 0;

        el.textContent = '0' + suffix;

        var timer = setInterval(function () {
            count++;
            current += step;
            if (count >= frames) {
                current = target;
                clearInterval(timer);
            }
            el.textContent = Math.round(current) + suffix;
        }, 16);  // ~60fps
    }

    // 兼容 DOM 已就绪和未就绪两种时序
    function onReady(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
    }

    onReady(function () {
        fetch('/api/stats', { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                animateNumber(document.getElementById('dashPaperCount'), d.paper_count || 0);
                animateNumber(document.getElementById('dashCatCount'), Object.keys(d.categories || {}).length);
                animateNumber(document.getElementById('dashInnoCount'), d.innovation_count || 0);
                animateNumber(document.getElementById('dashConfAvg'), Math.round((d.avg_confidence || 0) * 100), '%');
            })
            .catch(function () {});
    });
})();

// ═══════════════════════════════════════════
// Toast 通知系统
// ═══════════════════════════════════════════

function showToast(message, type) {
    type = type || 'info';
    var colors = { success: '#10b981', danger: '#ef4444', warning: '#f59e0b', info: '#4a6cf7' };
    var toast = document.createElement('div');
    toast.className = 'innocite-toast';
    toast.textContent = message;
    toast.style.cssText =
        'position:fixed;top:20px;right:20px;z-index:9999;padding:12px 24px;border-radius:10px;' +
        'color:#fff;font-weight:600;font-size:.9rem;box-shadow:0 8px 24px rgba(0,0,0,.2);' +
        'background:' + (colors[type] || colors.info) + ';' +
        'animation:toastIn .3s ease-out;max-width:360px;';
    document.body.appendChild(toast);
    setTimeout(function () {
        toast.style.animation = 'toastOut .3s ease-in forwards';
        setTimeout(function () { if (toast.parentNode) toast.remove(); }, 300);
    }, 3000);
}

// Toast 动画注入
(function () {
    var style = document.createElement('style');
    style.textContent =
        '@keyframes toastIn { from{opacity:0;transform:translateX(60px);} to{opacity:1;transform:translateX(0);} }' +
        '@keyframes toastOut{ from{opacity:1;transform:translateX(0);} to{opacity:0;transform:translateX(60px);} }';
    document.head.appendChild(style);
})();

// ═══════════════════════════════════════════
// 删除确认
// ═══════════════════════════════════════════

async function confirmDeletePaper(paperId, paperTitle) {
    var confirmMsg = '确定要删除以下论文吗？\n\n' + paperTitle +
        '\n\n此操作将同时删除关联的创新点、向量嵌入和推荐记录，且不可恢复。';

    if (!confirm(confirmMsg)) return;

    try {
        var resp = await fetch('/papers/' + paperId + '/delete', { method: 'POST' });
        var data = await resp.json();

        if (data.success) {
            // 如果在详情页（路径包含 /papers/数字），跳回首页
            var path = window.location.pathname;
            if (path.match(/^\/papers\/\d+$/)) {
                window.location.href = '/';
            } else {
                window.location.reload();
            }
        } else {
            alert('删除失败: ' + data.message);
        }
    } catch (e) {
        alert('删除请求失败: ' + e.message);
    }
}

// ═══════════════════════════════════════════
// 批量操作
// ═══════════════════════════════════════════

function updateBatchBar() {
    const checked = document.querySelectorAll('.paper-checkbox:checked');
    const bar = document.getElementById('batchBar');
    const count = document.getElementById('batchCount');
    const selectAll = document.getElementById('selectAll');

    if (checked.length === 0) {
        bar.classList.add('d-none');
    } else {
        bar.classList.remove('d-none');
        count.textContent = `已选 ${checked.length} 篇`;
    }
    selectAll.checked = false;
}

function toggleAllCheckboxes(el) {
    document.querySelectorAll('.paper-checkbox').forEach(cb => {
        cb.checked = el.checked;
    });
    updateBatchBar();
}

function toggleSelectAll() {
    const all = document.querySelectorAll('.paper-checkbox');
    const allChecked = Array.from(all).every(cb => cb.checked);
    all.forEach(cb => cb.checked = !allChecked);
    updateBatchBar();
}

async function batchOp(action) {
    const checked = document.querySelectorAll('.paper-checkbox:checked');
    const ids = Array.from(checked).map(cb => parseInt(cb.value));
    if (!ids.length) return;

    let category = null;
    if (action === 'set-category') {
        category = document.getElementById('batchCategory').value;
        if (!category) { alert('请选择目标学科'); return; }
    }

    if (action === 'delete' && !confirm(`确定要删除选中的 ${ids.length} 篇论文吗？此操作不可撤销。`)) {
        return;
    }

    const body = { paper_ids: ids, action: action };
    if (category) body.category = category;

    try {
        const resp = await fetch('/api/papers/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
            body: JSON.stringify(body),
            credentials: 'same-origin',
        });
        const data = await resp.json();
        if (data.success) {
            alert(data.message);
            window.location.reload();
        } else {
            alert('操作失败: ' + (data.message || '未知错误'));
        }
    } catch (e) {
        alert('请求失败: ' + e.message);
    }
}

// ═══════════════════════════════════════════
// 收藏功能
// ═══════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    // 加载已收藏状态
    const btns = document.querySelectorAll('.bookmark-btn');
    if (!btns.length) return;

    const ids = Array.from(btns).map(b => b.dataset.paperId).join(',');
    fetch(`/api/bookmarks/check?paper_ids=${ids}`, { credentials: 'same-origin' })
        .then(r => r.json())
        .then(d => {
            const bookmarked = d.data || [];
            btns.forEach(btn => {
                const pid = parseInt(btn.dataset.paperId);
                if (bookmarked.includes(pid)) {
                    setBookmarkIcon(btn, true);
                }
            });
        })
        .catch(() => {});
});

function toggleBookmark(btn, paperId) {
    const isBookmarked = btn.querySelector('i').classList.contains('bi-bookmark-star-fill');
    const method = isBookmarked ? 'DELETE' : 'POST';

    fetch(`/api/bookmarks/${paperId}`, {
        method: method,
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': getCSRFToken() },
    })
    .then(r => r.json())
    .then(d => {
        if (d.success) {
            setBookmarkIcon(btn, !isBookmarked);
        }
    })
    .catch(e => console.error('Bookmark error', e));
}

function setBookmarkIcon(btn, bookmarked) {
    const icon = btn.querySelector('i');
    if (bookmarked) {
        icon.className = 'bi bi-bookmark-star-fill text-warning';
        btn.title = '取消收藏';
    } else {
        icon.className = 'bi bi-bookmark-plus';
        btn.title = '收藏';
    }
}
