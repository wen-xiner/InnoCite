# -*- coding: utf-8 -*-
"""PDF 解析双轨回退流程图"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(11, 15))
ax.set_xlim(0, 11)
ax.set_ylim(0, 15)
ax.set_aspect("equal")
ax.axis("off")

C_BG  = "#D4E6F9"    # 浅蓝
C_TXT = "#1a1a1a"     # 黑色
C_BDR = "#B8D4F0"     # 边框
C_LN  = "#3B82C4"     # 连线
C_DSH = "#7CA9D8"     # 虚线
C_RED = "#E8A0A0"     # 失败/回退浅红
C_GRN = "#B0D8B0"     # 成功浅绿
C_GRY = "#F0F0F0"     # 灰色

def box(ax, x, y, w, h, text, bg="white", fs=7.5, bold=False, color=C_TXT, align="center"):
    r = FancyBboxPatch((x-w/2, y-h/2), w, h, boxstyle="round,pad=0.05",
                       facecolor=bg, edgecolor=C_BDR, linewidth=1.0, zorder=3)
    ax.add_patch(r)
    lines = text.split("\n")
    th = h / len(lines)
    for i, line in enumerate(lines):
        ly = y + h/2 - th*(i+0.5)
        ax.text(x, ly, line, ha=align, va="center", fontsize=fs,
                fontweight="bold" if bold else "normal", color=color, zorder=5)

def arrow(ax, x1, y1, x2, y2, lw=1.1, clr=C_LN):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=clr, lw=lw,
                                connectionstyle="arc3,rad=0"), zorder=2)

def diamond(ax, x, y, w, h, text, bg="white", fs=7):
    """菱形判断框"""
    pts = [(x, y+h/2), (x+w/2, y), (x, y-h/2), (x-w/2, y)]
    from matplotlib.patches import Polygon
    p = Polygon(pts, facecolor=bg, edgecolor=C_BDR, linewidth=1.0, zorder=3)
    ax.add_patch(p)
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, color=C_TXT, zorder=5)

# ═══════════════ 标题 ═══════════════
ax.set_title("PDF 论文解析 — 双轨回退流程图\nGROBID 机器学习 + pdfplumber 规则引擎",
             fontsize=13, fontweight="bold", pad=8, color="#1E3A5F")

# ═══════════════ 上传校验阶段 ═══════════════
box(ax, 5.5, 14.5, 3.2, 0.5, "用户上传 PDF 文件", bg=C_BG, fs=8, bold=True)
arrow(ax, 5.5, 14.25, 5.5, 13.95)

diamond(ax, 5.5, 13.65, 3.2, 0.7, "魔数签名校验\n(文件头 %PDF- 开头)?")

# 校验失败 → 拒绝
arrow(ax, 7.1, 13.65, 9.5, 13.65, clr=C_RED)
box(ax, 9.5, 13.65, 1.6, 0.45, "拒绝上传", bg=C_RED, fs=7, bold=True)

# 校验通过 ↓
arrow(ax, 5.5, 13.3, 5.5, 13.0)
box(ax, 5.5, 12.7, 3.0, 0.45, "文件暂存 uploads 目录", bg=C_GRY, fs=7.5)

# ═══════════════ GROBID 优先通道 ═══════════════
arrow(ax, 5.5, 12.45, 5.5, 12.15, lw=1.3)
box(ax, 5.5, 11.8, 5.2, 0.55, "GROBID 优先通道\nHTTP 调用 /api/processHeaderDocument", bg=C_BG, fs=8, bold=True)

arrow(ax, 5.5, 11.5, 5.5, 11.15)

diamond(ax, 5.5, 10.7, 4.0, 0.85, "GROBID 返回有效标题?\n(服务在线 + 标题非空)")

# GROBID 成功 → 完成
arrow(ax, 7.5, 10.7, 9.8, 10.7, clr=C_GRN)
box(ax, 9.8, 10.7, 2.2, 0.55, "解析成功\n返回论文元数据", bg=C_GRN, fs=7.5, bold=True)

# GROBID 失败 → 回退
arrow(ax, 5.5, 10.25, 5.5, 9.9, clr=C_RED)
box(ax, 5.5, 9.6, 4.0, 0.45, "回退至 pdfplumber 本地解析", bg=C_RED, fs=7.5, bold=True, color="#8B0000")

# ═══════════════ pdfplumber 五步回退通道 ═══════════════
arrow(ax, 5.5, 9.35, 5.5, 9.1)

# 左侧竖线
ax.plot([2.0, 2.0], [8.9, 3.0], color=C_LN, linewidth=1.5, zorder=1)
# 步骤标签
ax.text(2.0, 8.55, "第\n一\n步", ha="center", va="center", fontsize=7, fontweight="bold", color=C_LN)

steps = [
    (5.5, 8.55, 4.8, 0.5, "提取前 20 页全文文本\n(通过 pdfplumber 逐页抽取)"),
    (5.5, 7.65, 4.8, 0.5, "读取 PDF 内置元数据\n(Title / Author 字段)"),
    (5.5, 6.75, 4.8, 0.65, "字体大小分析提取标题\n取页面中间区域最大字体的非页眉页脚文本行"),
    (5.5, 5.65, 4.8, 0.65, "位置启发式提取标题\n取前 15 行中字母占比 > 65% 的最长行"),
    (5.5, 4.55, 4.8, 0.5, "四模式正则匹配摘要"),
    (5.5, 3.65, 4.8, 0.5, "五级年份提取"),
    (5.5, 2.75, 4.8, 0.5, "作者提取"),
]

for i, (x, y, w, h, text) in enumerate(steps):
    box(ax, x, y, w, h, text, bg="white" if i > 0 else C_BG, fs=7.2, bold=(i==0))
    if i < len(steps) - 1:
        arrow(ax, x, y - h/2, x, y + h/2 - (steps[i+1][2]/2 if False else 0) - 0.3)

# 连线调整
for i in range(len(steps) - 1):
    arrow(ax, 5.5, steps[i][1] - steps[i][3]/2, 5.5, steps[i+1][1] + steps[i+1][3]/2)

# ═══════════════ 子步骤展开 ═══════════════
# 四模式正则
box(ax, 9.5, 4.55, 2.5, 0.95,
    '标准 Abstract 标题\n中文「摘要」标题\n弱分隔匹配\n宽松匹配',
    bg="#F8F8F8", fs=6.8)

# 五级年份
box(ax, 9.5, 3.65, 2.5, 0.95,
    "PDF 元数据日期\n版权标记 ©\n会议名称年份\n发表日期\n通用年份正则",
    bg="#F8F8F8", fs=6.8)

# 作者提取
box(ax, 9.5, 2.75, 2.5, 0.8,
    "IEEE/ACM 格式\n作者标签匹配\n标题后文本块匹配",
    bg="#F8F8F8", fs=6.8)

darrow = lambda ax, x1, y1, x2, y2: ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
    arrowprops=dict(arrowstyle="->", color=C_DSH, lw=0.7, linestyle="dashed",
                    connectionstyle="arc3,rad=0"), zorder=1)

darrow(ax, 7.9, 4.55, 8.25, 4.55)
darrow(ax, 7.9, 3.65, 8.25, 3.65)
darrow(ax, 7.9, 2.75, 8.25, 2.75)

# ═══════════════ 最终输出 ═══════════════
arrow(ax, 5.5, 2.25, 5.5, 1.8)
box(ax, 5.5, 1.4, 4.5, 0.55, "组装结果 → 清理临时文件 → 返回论文数据", bg=C_GRN, fs=7.8, bold=True)

# ═══════════════ 图中标注 ═══════════════
# GROBID 阶段标签
ax.text(0.8, 11.5, "GROBID\n优先通道", ha="center", va="center", fontsize=7,
        fontweight="bold", color=C_LN, rotation=90)

ax.text(0.8, 6.0, "pdfplumber 回退通道 (5步)", ha="center", va="center", fontsize=7,
        fontweight="bold", color=C_RED, rotation=90)

ax.text(8.5, 9.8, "GROBID\n失败触发回退", ha="center", va="center", fontsize=6.5,
        color="#8B0000", bbox=dict(boxstyle="round,pad=0.1", facecolor="white",
        edgecolor=C_RED, alpha=0.9, linewidth=0.3), zorder=5)

for fmt in ["png", "svg", "pdf"]:
    path = os.path.join(OUTPUT_DIR, f"PDF_Parse_Flow.{fmt}")
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"[OK] {path}")

plt.close(fig)
print("\n[Done]")
