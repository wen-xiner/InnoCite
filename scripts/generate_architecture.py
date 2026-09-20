# -*- coding: utf-8 -*-
"""InnoCite 三层架构图 — 简洁清晰版"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(11, 10))
ax.set_xlim(0, 11)
ax.set_ylim(0, 10)
ax.set_aspect("equal")
ax.axis("off")

C_BG   = "#D4E6F9"   # 浅蓝标题/层背景
C_TXT  = "#1a1a1a"   # 黑色文字
C_BDR  = "#B8D4F0"   # 边框
C_LINE = "#3B82C4"   # 连线
C_DASH = "#7CA9D8"   # 虚线

def box(ax, x, y, w, h, text, bg="white", fs=8, bold=False):
    r = FancyBboxPatch((x-w/2, y-h/2), w, h, boxstyle="round,pad=0.05",
                       facecolor=bg, edgecolor=C_BDR, linewidth=1.0, zorder=3)
    ax.add_patch(r)
    ax.text(x, y, text, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", color=C_TXT, zorder=5)

def arrow(ax, x1, y1, x2, y2, style="solid", lw=1.2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=C_LINE, lw=lw,
                                linestyle=style, connectionstyle="arc3,rad=0"), zorder=1)

def darrow(ax, x1, y1, x2, y2):
    arrow(ax, x1, y1, x2, y2, style="dashed", lw=0.9)

# ═══════════════ 三层背景 ═══════════════
for y0, h, label in [(7.5, 2.2, "表 示 层"), (4.5, 2.5, "业 务 逻 辑 层"), (1.2, 2.8, "数 据 持 久 层")]:
    r = FancyBboxPatch((0.6, y0), 9.8, h, boxstyle="round,pad=0.08",
                       facecolor="#F5F9FD", edgecolor=C_BDR, linewidth=0.8, zorder=0)
    ax.add_patch(r)
    ax.text(1.0, y0 + h - 0.3, label, fontsize=9, fontweight="bold", color=C_LINE, zorder=5)

# ═══════════════ 表示层 ═══════════════
box(ax, 1.6, 9.3, 1.6, 0.5, "浏览器", fs=8, bold=True)
box(ax, 5.5, 9.3, 4.5, 0.55, "Flask 应用工厂 (路由 + 蓝图 + 中间件)", bg=C_BG, fs=8.5, bold=True)
box(ax, 9.4, 9.3, 1.6, 0.5, "Jinja2 模板引擎", fs=8)

arrow(ax, 2.4, 9.3, 3.25, 9.3)
arrow(ax, 7.75, 9.3, 8.6, 9.3)

# 8个蓝图简要标注
box(ax, 5.5, 8.3, 5.5, 0.35, "8个蓝图: 认证 | 论文 | 创新点 | 趋势 | 推荐 | 报告 | 管理 | 评估", fs=7)

# ═══════════════ 业务逻辑层 ═══════════════
mods = [
    (2.0, 6.3, 2.4, 0.9, "论文解析器\n(6种导入方式)"),
    (5.0, 6.3, 2.6, 0.9, "创新点提取器\n(LLM + 规则双轨)"),
    (8.2, 6.3, 2.8, 0.9, "关键词趋势分析器\n(KeyBERT + TF-IDF)"),
    (2.6, 4.8, 2.6, 0.9, "大模型客户端\n(DeepSeek API)"),
    (5.8, 4.8, 2.6, 0.9, "跨学科推荐器\n(SBERT + TF-IDF)"),
    (8.8, 4.8, 2.4, 0.9, "报告生成器\n(PDF + 图表)"),
]
for x, y, w, h, t in mods:
    box(ax, x, y, w, h, t, bg=C_BG if "论文" in t else "white", fs=7.2, bold="论文" in t)

# ═══════════════ 数据持久层 ═══════════════
box(ax, 5.5, 3.3, 4.5, 0.5, "SQLAlchemy ORM (数据库引擎 + 迁移管理)", bg=C_BG, fs=8, bold=True)

models = ["论文\n(Paper)", "创新点\n(Innovation)", "向量嵌入\n(Embedding)", "推荐结果\n(Recommend)", "用户\n(User)", "缓存\n(Cache)"]
for i, m in enumerate(models):
    box(ax, 1.3 + i*1.65, 1.8, 1.4, 0.8, m, fs=7)

# ── 层间连线 ──
arrow(ax, 5.5, 7.8, 6.8, 6.75, lw=1.5)   # Flask → 论文解析器
arrow(ax, 5.5, 7.8, 3.2, 6.75, lw=1.5)   # Flask → 创新点
arrow(ax, 5.5, 7.8, 1.6, 5.25, lw=1.2)   # Flask → LLM
arrow(ax, 5.5, 3.05, 3.0, 2.2, lw=1.5)   # ORM → 论文
arrow(ax, 5.5, 3.05, 7.5, 2.2, lw=1.5)   # ORM → 推荐

# 业务层内部
darrow(ax, 3.2, 5.7, 2.6, 5.25)  # 创新点 → LLM
darrow(ax, 7.0, 5.7, 5.8, 5.25)  # 趋势 → 推荐

# 外部服务
darrow(ax, 2.0, 6.3, 0.3, 7.5)
darrow(ax, 2.6, 4.8, 0.3, 5.5)
box(ax, 0.1, 6.5, 0.4, 2.2, "外\n部\n服\n务", fs=6.5, bg="#F0F0F0")

# ── 图例 ──
leg = [
    plt.Line2D([0],[0], color=C_LINE, lw=1.5, label="数据流 / 调用"),
    plt.Line2D([0],[0], color=C_DASH, lw=0.9, ls="dashed", label="依赖关系"),
]
ax.legend(handles=leg, loc="lower right", fontsize=7, title="连线", title_fontsize=8,
          framealpha=0.95, edgecolor=C_BDR)

ax.set_title("InnoCite 系统 — 三层架构设计图\n表示层 / 业务逻辑层 / 数据持久层",
             fontsize=13, fontweight="bold", pad=6, color="#1E3A5F")

for fmt in ["png", "svg", "pdf"]:
    path = os.path.join(OUTPUT_DIR, f"Architecture_Diagram.{fmt}")
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    print(f"[OK] {path}")

plt.close(fig)
print("\n[Done]")
