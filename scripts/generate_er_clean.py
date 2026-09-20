# -*- coding: utf-8 -*-
"""InnoCite E-R 图 — 紧凑布局 + 浅蓝白配色 + 黑色文字"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np, os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(12, 12))
ax.set_xlim(0, 12)
ax.set_ylim(0, 12)
ax.set_aspect("equal")
ax.axis("off")

# ── 配色 ──
HEADER_BG  = "#D4E6F9"   # 浅蓝标题栏
HEADER_TXT = "#1a1a1a"   # 标题黑色
BODY_BG    = "#FFFFFF"
BORDER     = "#B8D4F0"
TEXT_CLR   = "#1a1a1a"
KEY_CLR    = "#1a1a1a"
EDGE_CLR   = "#3B82C4"
EDGE_DASH  = "#7CA9D8"
EDGE_DOT   = "#A8C8E8"

def entity(ax, cx, cy, w, h, title, fields):
    """紧凑实体框：缩小白边，黑色文字"""
    # 外框
    r = FancyBboxPatch((cx-w/2, cy-h/2), w, h, boxstyle="round,pad=0.04",
                       facecolor=BODY_BG, edgecolor=BORDER, linewidth=1.0, zorder=3)
    ax.add_patch(r)
    # 标题栏（紧凑）
    th = 0.38
    tr = plt.Rectangle((cx-w/2+0.01, cy+h/2-th), w-0.02, th,
                       facecolor=HEADER_BG, edgecolor="none", zorder=4)
    ax.add_patch(tr)
    ax.text(cx, cy+h/2-th/2, title, ha="center", va="center",
            fontsize=8.5, fontweight="bold", color=HEADER_TXT, zorder=5)
    # 字段 — 压缩行距
    n = len(fields)
    avail_h = h - th - 0.06
    row_h = min(0.36, avail_h / n)
    y0 = cy + h/2 - th - 0.02

    for i, (txt, is_key) in enumerate(fields):
        y = y0 - row_h * (i + 0.5)
        # 截断检测
        max_chars = int((w - 0.3) / 0.10)
        if len(txt) > max_chars:
            txt = txt[:max_chars-1]
        if is_key:
            ax.text(cx-w/2+0.18, y, txt, ha="left", va="center",
                    fontsize=7.8, color=TEXT_CLR, fontweight="bold")
        else:
            ax.text(cx-w/2+0.18, y, txt, ha="left", va="center",
                    fontsize=7.5, color=TEXT_CLR)

def link(ax, x1, y1, x2, y2, label, lx, ly, style="solid", lw=1.4, clr=EDGE_CLR):
    """连线 + 手动指定标签坐标 (lx,ly) 避免重叠"""
    ax.plot([x1, x2], [y1, y2], color=clr, linewidth=lw, linestyle=style, zorder=0)
    ax.text(lx, ly, label, ha="center", va="center", fontsize=6.0,
            color=clr, bbox=dict(boxstyle="round,pad=0.10", facecolor="white",
                                 edgecolor=clr, alpha=0.92, linewidth=0.3), zorder=5)

# ═══════════════ 紧凑正方形布局 ═══════════════
P = (6.0, 7.0, 4.0, 3.6)     # 论文（居中）
I = (10.3, 10.5, 4.0, 3.2)   # 创新点（右上）
E = (1.7, 10.5, 4.0, 1.8)    # 向量嵌入（左上）
R = (10.3, 2.8, 4.0, 2.4)    # 推荐结果（右下）
U = (1.7, 2.0, 3.4, 2.0)     # 用户（左下）
B = (5.8, 2.0, 3.0, 1.2)     # 收藏关联（中下）
K = (10.3, 0.5, 4.0, 1.8)    # 关键词缓存（最右下）

# ── 绘制 ──
entity(ax, *P, "论文 (Paper)", [
    ("[主] 编号  /  arXiv编号", True),
    ("标题 / 作者 / 年份 / 发表场合", False),
    ("摘要 / 全文 / 学科分类", False),
    ("来源类型 / 状态 / 创建时间", False),
])

entity(ax, *I, "创新点 (Innovation)", [
    ("[主] 编号", True),
    ("[外码·唯一] 论文编号", True),
    ("问题陈述 / 方法描述", False),
    ("效果描述 / 置信度 / 是否确认", False),
])

entity(ax, *E, "向量嵌入 (PaperEmbedding)", [
    ("[主] 编号", True),
    ("[外码·唯一] 论文编号", True),
    ("向量数据(384维) / 创建时间", False),
])

entity(ax, *R, "推荐结果 (Recommendation)", [
    ("[主] 编号", True),
    ("[外码] 源论文编号 / 目标论文编号", True),
    ("相似度 / 推荐理由 / 创建时间", False),
])

entity(ax, *U, "用户 (User)", [
    ("[主] 编号", True),
    ("用户名 / 显示名称", False),
    ("是否激活 / 创建时间", False),
])

entity(ax, *K, "关键词缓存 (KeywordCache)", [
    ("[主] 编号", True),
    ("缓存键 / 缓存数据(JSON)", False),
    ("论文数量 / 配置版本号 / 更新时间", False),
])

entity(ax, *B, "收藏关联", [
    ("[主·外码] 用户编号", True),
    ("[主·外码] 论文编号", True),
])

# ── 连线（每条手动指定标签坐标以避免重叠）──
# 1. Paper → Innovation（右上）：标签放在线段右侧偏上
link(ax, P[0]+2.0, P[1]+1.0, I[0]-2.0, I[1]-1.4,
     "1:1  拥有创新点", lx=9.5, ly=8.9, lw=2.0)
# 2. Paper → Embedding（左上）：标签放在线段左侧
link(ax, P[0]-2.0, P[1]+1.0, E[0]+2.0, E[1]-0.2,
     "1:1  拥有向量嵌入", lx=2.8, ly=9.5, lw=2.0)
# 3. Paper → Recommend（右下）：标签放在线段右上方
link(ax, P[0]+1.0, P[1]-1.8, R[0], R[1]+1.2,
     "1:N  产生推荐", lx=9.8, ly=5.2, lw=1.4)
# 4. Recommend → Paper（虚线回退）：标签放在线段左下方
link(ax, R[0]-1.8, R[1]+1.1, P[0]-1.0, P[1]-1.8,
     "N:1  目标论文", lx=5.8, ly=4.4, style="dashed", lw=1.0, clr=EDGE_DASH)
# 5. User → Bookmark（左下）：标签放在线段下方
link(ax, U[0]+1.7, U[1]+0.5, B[0]-1.5, B[1]+0.1,
     "1:N  收藏记录", lx=3.9, ly=1.8, lw=1.4)
# 6. Paper → Bookmark（中下）：标签放在线段左侧
link(ax, P[0]-0.5, P[1]-1.8, B[0], B[1]+0.6,
     "1:N  被收藏", lx=4.5, ly=3.9, lw=1.4)
# 7. Paper → KeywordCache（点线右下）：标签放在右边远离其他标签
link(ax, P[0]+1.5, P[1]-1.2, K[0], K[1]+0.9,
     "事件触发同步", lx=10.0, ly=3.2, style="dotted", lw=0.8, clr=EDGE_DOT)

ax.annotate("M : N\n(多对多)", xy=(B[0]-1.5, B[1]-0.65),
            fontsize=5.8, color=EDGE_CLR, ha="center", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.12", facecolor="white",
                      edgecolor=EDGE_CLR, alpha=0.85, linewidth=0.3))

# ── 图例 ──
leg = [
    plt.Line2D([0],[0], color=EDGE_CLR, lw=2.0, label="1:1  一对一"),
    plt.Line2D([0],[0], color=EDGE_CLR, lw=1.4, label="1:N  一对多"),
    plt.Line2D([0],[0], color=EDGE_DASH, lw=1.0, ls="dashed", label="N:1  反向引用"),
    plt.Line2D([0],[0], color=EDGE_DOT, lw=0.8, ls="dotted", label="事件触发同步"),
]
ax.legend(handles=leg, loc="lower right", fontsize=6.2, title="关系类型", title_fontsize=7,
          framealpha=0.95, edgecolor=BORDER)

ax.set_title("InnoCite 系统 — 实体关系图 (E-R Diagram)\n基于 SQLAlchemy ORM 数据模型",
             fontsize=12, fontweight="bold", pad=6, color="#1E3A5F")

ax.text(6.0, 11.85, "[主] = 主键    [外码] = 外键    1:1 一对一    1:N 一对多    M:N 多对多",
        ha="center", fontsize=6.5, color="#A0AEC0")

for fmt in ["png", "svg", "pdf"]:
    path = os.path.join(OUTPUT_DIR, f"ER_Diagram_Clean.{fmt}")
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"[OK] {path}")

plt.close(fig)
print("\n[Done]")
