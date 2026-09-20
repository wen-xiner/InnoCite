# -*- coding: utf-8 -*-
"""使用 Matplotlib 手工绘制 InnoCite 系统实体关系图 (E-R图) — 中文版"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np
import os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 全局字体设置
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

# 颜色方案
COLORS = {
    "论文": ("#DAA520", "#FFF8DC"),
    "创新点": ("#4682B4", "#F0F8FF"),
    "向量嵌入": ("#3CB371", "#F5FFFA"),
    "推荐结果": ("#DB7093", "#FFF0F5"),
    "用户": ("#CD853F", "#FFF5EE"),
    "关键词缓存": ("#6B8E23", "#F0FFF0"),
    "收藏关联": ("#BDB76B", "#FAFAD2"),
}

fig, ax = plt.subplots(1, 1, figsize=(24, 18))
ax.set_xlim(0, 24)
ax.set_ylim(0, 18)
ax.set_aspect("equal")
ax.axis("off")

# ── 辅助函数 ──
def draw_entity(ax, x, y, w, h, title, fields, color, light_color):
    """绘制实体矩形框（中文）"""
    # 外框
    rect = FancyBboxPatch((x - w/2, y - h/2), w, h,
                          boxstyle="round,pad=0.12", facecolor=light_color,
                          edgecolor=color, linewidth=2.2, zorder=3)
    ax.add_patch(rect)
    # 标题栏
    title_h = 0.55
    title_rect = FancyBboxPatch((x - w/2, y + h/2 - title_h), w, title_h,
                                boxstyle="round,pad=0.03", facecolor=color,
                                edgecolor=color, linewidth=0, zorder=4)
    ax.add_patch(title_rect)
    ax.text(x, y + h/2 - title_h/2, title, ha="center", va="center",
            fontsize=9.5, fontweight="bold", color="white", zorder=5)
    # 字段行
    y_start = y + h/2 - title_h - 0.08
    row_h = 0.36
    for i, (name, is_key) in enumerate(fields):
        fy = y_start - row_h * (i + 0.6)
        if is_key:
            label = f"[主] {name}"
            ax.text(x - w/2 + 0.2, fy, label, ha="left", va="center",
                    fontsize=7.2, color="#222", zorder=5, fontweight="bold")
        elif is_key is None:
            # 副标题分隔行
            ax.text(x, fy, name, ha="center", va="center",
                    fontsize=6.5, color="#999", zorder=5, style="italic")
        else:
            ax.text(x - w/2 + 0.2, fy, f"    {name}", ha="left", va="center",
                    fontsize=7.2, color="#444", zorder=5)
    return x, y, w, h


def draw_rel_line(ax, x1, y1, x2, y2, label, color, style="solid", lw=1.8):
    """绘制关系线并标注"""
    ax.plot([x1, x2], [y1, y2], color=color, linewidth=lw,
            linestyle=style, zorder=1)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    length = np.hypot(dx, dy)
    if length > 0:
        nx, ny = -dy / length * 1.2, dx / length * 1.2
    else:
        nx, ny = 0, 0
    ax.text(mx + nx, my + ny, label, ha="center", va="center",
            fontsize=7.5, color=color, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      edgecolor=color, alpha=0.9, linewidth=0.8), zorder=6)


# ═══════════════════════ 布局坐标 ═══════════════════════
# Paper（论文）— 居中偏上
px, py = 12.0, 10.5
# Innovation（创新点）— 右侧上方
ix, iy = 21.0, 15.0
# PaperEmbedding（向量嵌入）— 左上方
ex, ey = 3.0, 15.0
# Recommendation（推荐结果）— 右侧下方
rx, ry = 21.0, 4.5
# User（用户）— 左下方
ux, uy = 3.0, 5.8
# KeywordCache（关键词缓存）— 右下角
kx, ky = 21.0, 1.0
# user_bookmarks（收藏关联）— User 与 Paper 之间
bx, by = 7.5, 8.0

# ═══════════════════════ 绘制实体 ═══════════════════════
draw_entity(ax, px, py, 4.8, 5.5, "论文 (Paper)",
            [("编号 (主码) : INTEGER", True),
             ("arXiv编号 : VARCHAR(50)", False),
             ("标题 : TEXT", False),
             ("作者 : TEXT", False),
             ("年份 : INTEGER", False),
             ("发表场合 : VARCHAR(255)", False),
             ("摘要 : TEXT", False),
             ("全文 : TEXT", False),
             ("学科分类 : VARCHAR(100)", False),
             ("来源类型 : VARCHAR(20)", False),
             ("状态 : VARCHAR(20)", False),
             ("创建时间 : DATETIME", False)],
            *COLORS["论文"])

draw_entity(ax, ix, iy, 4.6, 3.8, "创新点 (Innovation)",
            [("编号 (主码) : INTEGER", True),
             ("论文编号 (外码,唯一) : INTEGER", True),
             ("解决的问题 : TEXT", False),
             ("采用的方法 : TEXT", False),
             ("达到的效果 : TEXT", False),
             ("完整陈述 : TEXT", False),
             ("置信度 : FLOAT", False),
             ("是否已确认 : BOOLEAN", False),
             ("更新时间 : DATETIME", False)],
            *COLORS["创新点"])

draw_entity(ax, ex, ey, 4.4, 2.2, "向量嵌入 (PaperEmbedding)",
            [("编号 (主码) : INTEGER", True),
             ("论文编号 (外码,唯一) : INTEGER", True),
             ("向量数据 (384维) : BLOB", False),
             ("创建时间 : DATETIME", False)],
            *COLORS["向量嵌入"])

draw_entity(ax, rx, ry, 4.6, 2.8, "推荐结果 (Recommendation)",
            [("编号 (主码) : INTEGER", True),
             ("源论文编号 (外码) : INTEGER", True),
             ("目标论文编号 (外码) : INTEGER", True),
             ("相似度 : FLOAT", False),
             ("推荐理由 : TEXT", False),
             ("创建时间 : DATETIME", False)],
            *COLORS["推荐结果"])

draw_entity(ax, ux, uy, 4.0, 2.6, "用户 (User)",
            [("编号 (主码) : INTEGER", True),
             ("用户名 : VARCHAR(64)", False),
             ("密码哈希 : VARCHAR(128)", False),
             ("显示名称 : VARCHAR(64)", False),
             ("是否激活 : BOOLEAN", False),
             ("创建时间 : DATETIME", False)],
            *COLORS["用户"])

draw_entity(ax, kx, ky, 4.6, 2.8, "关键词缓存 (KeywordCache)",
            [("编号 (主码) : INTEGER", True),
             ("缓存键 : VARCHAR(64)", False),
             ("缓存数据 : JSON", False),
             ("论文数量 : INTEGER", False),
             ("配置版本号 : VARCHAR(32)", False),
             ("更新时间 : DATETIME", False)],
            *COLORS["关键词缓存"])

draw_entity(ax, bx, by, 3.6, 1.4, "收藏关联 (user_bookmarks)",
            [("用户编号 (外码,主码) : INTEGER", True),
             ("论文编号 (外码,主码) : INTEGER", True)],
            *COLORS["收藏关联"])

# ═══════════════════════ 绘制关系连线 ═══════════════════════

# 论文 ↔ 创新点 (1:1)
draw_rel_line(ax, px + 2.4, py + 0.8, ix - 2.3, iy - 1.5,
              "1 : 1\n拥有一项创新点", COLORS["创新点"][0], lw=2.2)

# 论文 ↔ 向量嵌入 (1:1)
draw_rel_line(ax, px - 2.4, py + 0.8, ex + 2.2, ey - 0.4,
              "1 : 1\n拥有一个向量嵌入", COLORS["向量嵌入"][0], lw=2.2)

# 论文 → 推荐结果 (1:N, 源论文)
draw_rel_line(ax, px + 1.5, py - 2.75, rx, ry + 1.4,
              "1 : N\n作为源论文产生推荐", COLORS["推荐结果"][0], lw=1.6)

# 推荐结果 → 论文 (N:1, 目标论文，虚线回退)
draw_rel_line(ax, rx - 1.2, ry + 1.3, px - 1.2, py - 2.75,
              "N : 1\n指向目标论文", COLORS["推荐结果"][0], style="dashed", lw=1.4)

# 用户 → user_bookmarks (1:N)
draw_rel_line(ax, ux + 2.0, uy + 0.6, bx - 1.8, by - 0.15,
              "1 : N\n创建收藏记录", COLORS["收藏关联"][0], lw=1.6)

# 论文 → user_bookmarks (1:N)
draw_rel_line(ax, px - 2.15, py - 2.2, bx + 1.8, by + 0.15,
              "1 : N\n被加入收藏", COLORS["收藏关联"][0], lw=1.6)

# 论文 → 关键词缓存（点线，事件触发同步）
draw_rel_line(ax, px + 2.0, py - 1.5, kx, ky + 1.4,
              "事件触发器同步\n(SQLAlchemy事件监听,\n论文增删时自动更新)",
              COLORS["关键词缓存"][0], style="dotted", lw=1.1)

# ═══════════════════════ M:N 标注 ═══════════════════════
ax.annotate("M : N\n(多对多收藏关系)",
            xy=(bx, by - 0.7), fontsize=7.5, color=COLORS["收藏关联"][0],
            fontweight="bold", ha="center", va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFFF0",
                      edgecolor=COLORS["收藏关联"][0], alpha=0.85))

# ═══════════════════════ 图例 ═══════════════════════
legend_entities = [
    mpatches.Patch(color=COLORS["论文"][0], alpha=0.35, label="论文 (Paper)"),
    mpatches.Patch(color=COLORS["创新点"][0], alpha=0.35, label="创新点 (Innovation)"),
    mpatches.Patch(color=COLORS["向量嵌入"][0], alpha=0.35, label="向量嵌入 (PaperEmbedding)"),
    mpatches.Patch(color=COLORS["推荐结果"][0], alpha=0.35, label="推荐结果 (Recommendation)"),
    mpatches.Patch(color=COLORS["用户"][0], alpha=0.35, label="用户 (User)"),
    mpatches.Patch(color=COLORS["关键词缓存"][0], alpha=0.35, label="关键词缓存 (KeywordCache)"),
    mpatches.Patch(color=COLORS["收藏关联"][0], alpha=0.35, label="收藏关联 (user_bookmarks)"),
]
leg1 = ax.legend(handles=legend_entities, loc="upper left",
                 fontsize=7, title="实体 (Entities)", title_fontsize=8.5,
                 ncol=2, framealpha=0.92)
ax.add_artist(leg1)

legend_lines = [
    plt.Line2D([0], [0], color="gray", linewidth=2.2, label="1:1 一对一"),
    plt.Line2D([0], [0], color="gray", linewidth=1.6, label="1:N 一对多"),
    plt.Line2D([0], [0], color="gray", linewidth=1.4, linestyle="dashed", label="反向引用 (目标论文N:1)"),
    plt.Line2D([0], [0], color="gray", linewidth=1.1, linestyle="dotted", label="事件触发同步"),
]
ax.legend(handles=legend_lines, loc="upper right",
          fontsize=7, title="关系 (Relations)", title_fontsize=8.5,
          framealpha=0.92)

# ═══════════════════════ 标题与说明 ═══════════════════════
ax.set_title("InnoCite 系统 — 实体关系图 (E-R Diagram)\n"
             "基于 SQLAlchemy ORM 的学术论文创新点提炼与跨学科推荐系统",
             fontsize=16, fontweight="bold", pad=14, color="#333")

ax.text(12.0, 17.6,
        "[主] = 主键 (Primary Key)    [外码] = 外键 (Foreign Key)    粗体字段 = 关键字段",
        ha="center", fontsize=7.5, color="#888", style="italic")

# ═══════════════════════ 保存 ═══════════════════════
for fmt in ["png", "svg", "pdf"]:
    path = os.path.join(OUTPUT_DIR, f"ER_Diagram_CN_Matplotlib.{fmt}")
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"[OK] Generated: {path}")

plt.close(fig)
print("\n[Done] Matplotlib Chinese ER Diagram generated!")
print(f"      Output directory: {OUTPUT_DIR}")
