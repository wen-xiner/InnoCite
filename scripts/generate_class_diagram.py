# -*- coding: utf-8 -*-
"""InnoCite 类图 — 全中文、框自适应文字长短、紧凑布局"""

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

HEADER_BG  = "#D4E6F9"   # 浅蓝标题栏（黑字可读）
HEADER_TXT = "#1a1a1a"   # 标题黑色
BODY_BG    = "#FFFFFF"
BORDER     = "#B8D4F0"
TEXT_CLR   = "#1a1a1a"
EDGE_CLR   = "#3B82C4"
EDGE_DASH  = "#7CA9D8"
EDGE_DOT   = "#A8C8E8"

def draw_arrow(ax, x1, y1, x2, y2, style="solid", lw=1.4, clr=EDGE_CLR, arrow="->"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=arrow, color=clr, lw=lw,
                                linestyle=style, connectionstyle="arc3,rad=0"),
                zorder=0)

def label_at(ax, lx, ly, text, clr=EDGE_CLR, fs=5.8):
    ax.text(lx, ly, text, ha="center", va="center", fontsize=fs,
            color=clr, bbox=dict(boxstyle="round,pad=0.10", facecolor="white",
                                 edgecolor=clr, alpha=0.92, linewidth=0.3), zorder=5)

def auto_w(all_lines):
    """根据最长行自动计算框宽"""
    max_len = max(len(s) for s in all_lines)
    # 中文约0.11英寸/字，留0.35英寸边距
    return max(2.8, min(5.0, max_len * 0.11 + 0.35))

def clazz(ax, cx, cy, name, attrs, methods):
    """自适应框大小"""
    all_lines = [name] + attrs + methods
    w = auto_w(all_lines)
    n_attr = len(attrs)
    n_meth = len(methods)
    # 标题0.38 + 属性行*0.28 + 方法行*0.28 + 分隔线空间
    h = 0.40 + n_attr * 0.28 + n_meth * 0.28 + 0.28

    r = FancyBboxPatch((cx-w/2, cy-h/2), w, h, boxstyle="round,pad=0.04",
                       facecolor=BODY_BG, edgecolor=BORDER, linewidth=1.0, zorder=3)
    ax.add_patch(r)
    th = 0.40
    tr = plt.Rectangle((cx-w/2+0.01, cy+h/2-th), w-0.02, th,
                       facecolor=HEADER_BG, edgecolor="none", zorder=4)
    ax.add_patch(tr)
    ax.text(cx, cy+h/2-th/2, name, ha="center", va="center",
            fontsize=8.5, fontweight="bold", color=HEADER_TXT, zorder=5)

    # 属性/方法分隔线
    sep_a = cy + h/2 - th
    ax.plot([cx-w/2+0.06, cx+w/2-0.06], [sep_a, sep_a], color=BORDER, linewidth=0.6, zorder=4)

    y = sep_a - 0.04
    for a in attrs:
        y -= 0.28
        ax.text(cx-w/2+0.15, y + 0.14, a, ha="left", va="center", fontsize=7.0, color=TEXT_CLR)

    sep_m = y - 0.10
    ax.plot([cx-w/2+0.06, cx+w/2-0.06], [sep_m, sep_m], color=BORDER, linewidth=0.6, zorder=4)

    y = sep_m - 0.04
    for m in methods:
        y -= 0.28
        ax.text(cx-w/2+0.15, y + 0.14, m, ha="left", va="center", fontsize=7.0, color=TEXT_CLR, style="italic")

    return (cx, cy, w, h)

# ═══════════════ 七个类（全中文 + 自适应框宽）═══════════════

# 中心：创新点提取器
IE = clazz(ax, 6.2, 7.8, "创新点提取器",
    ["- 大模型可用 : bool", "- 规则提取器实例", "- 大模型客户端实例"],
    ["+ 提取创新点(论文) : 字典", "+ 大模型通道提取(文本) : 字典", "+ 规则通道提取(文本) : 字典"])

# 左上：规则引擎提取器
RI = clazz(ax, 1.5, 11.2, "规则引擎提取器",
    ["+ 问题触发词 : 列表(36个)", "+ 方法触发词 : 列表(28个)", "+ 效果触发词 : 列表(22个)"],
    ["+ 提取(文本) : 字典", "+ 分句(文本) : 列表", "+ 计算置信度(三维度) : 小数"])

# 右上：大模型客户端
LC = clazz(ax, 10.8, 11.2, "大模型客户端",
    ["- 接口密钥 : 字符串", "- 模型 = deepseek-v4-pro", "- 缓存 : LRU(最大200条)"],
    ["+ 提取创新点(标题,摘要) : 字典", "+ 生成推荐理由(源,目标) : 字符串", "+ 论文分类(摘要) : 字符串", "+ 生成综述(论文列表) : 字符串"])

# 左中：论文解析器
PP = clazz(ax, 1.5, 7.2, "论文解析器",
    ["- GROBID服务地址", "- 上传目录"],
    ["+ 通过ID导入(arxiv编号) : 论文", "+ 搜索导入(关键词,数量) : 列表", "+ 导入CSV(文件) : 列表", "+ 导入PDF(文件) : 论文", "+ 导入EndNote(文件) : 列表", "+ 导入BibTeX(文件) : 列表"])

# 右中：跨学科推荐器
RC = clazz(ax, 10.8, 7.2, "跨学科推荐器",
    ["- SBERT管理器单例", "- TF-IDF向量化器", "- TF-IDF稀疏矩阵"],
    ["+ 推荐(论文编号,数量) : 列表", "+ SBERT相似度(源,候选) : 数组", "+ TF-IDF相似度(源,候选) : 数组", "+ 重建缓存() : 空"])

# 左下：报告生成器
RG = clazz(ax, 1.2, 2.0, "报告生成器",
    ["- 中文字体注册", "- 段落样式表"],
    ["+ 生成PDF(论文编号) : 字节", "+ 嵌入图表(内容流) : 空", "+ 绘制页码(画布,文档) : 空"])

# 中下：关键词趋势分析器
KT = clazz(ax, 6.2, 2.0, "关键词趋势分析器",
    ["- KeyBERT模型", "- TF-IDF向量化器", "- 缓存字典"],
    ["+ 提取关键词(方法) : 列表", "+ 计算热度矩阵() : 字典", "+ 趋势预测(关键词) : 字典", "+ 生成河流图数据() : 字典", "+ 追踪方法迁移(源,目标) : 列表"])

# ═══════════════ 关系连线 ═══════════════

# 1. 创新点提取器 ◆→ 规则引擎提取器（组合）
draw_arrow(ax, IE[0]-IE[2]/2, IE[1]+IE[3]/2-0.3, RI[0]+RI[2]/2, RI[1]-RI[3]/2+0.3, lw=1.6)
label_at(ax, 3.2, 9.9, "组合\n持有实例")

# 2. 创新点提取器 --> 大模型客户端（依赖）
draw_arrow(ax, IE[0]+IE[2]/2, IE[1]+IE[3]/2-0.3, LC[0]-LC[2]/2, LC[1]-LC[3]/2+0.3,
           style="dashed", lw=1.1, clr=EDGE_DASH)
label_at(ax, 9.2, 9.9, "依赖\n调用大模型API")

# 3. 创新点提取器 --> 论文解析器（依赖）
draw_arrow(ax, IE[0]-0.6, IE[1]-IE[3]/2, PP[0]+PP[2]/2, PP[1]+PP[3]/2,
           style="dashed", lw=1.1, clr=EDGE_DASH)
label_at(ax, 3.0, 7.0, "依赖\n读取论文数据", fs=5.5)

# 4. 跨学科推荐器 --> 大模型客户端（依赖）
draw_arrow(ax, RC[0], RC[1]+RC[3]/2, LC[0], LC[1]-LC[3]/2,
           style="dashed", lw=1.1, clr=EDGE_DASH)
label_at(ax, 11.5, 10.0, "依赖\n生成推荐理由", fs=5.5)

# 5. 跨学科推荐器 --> 创新点提取器（依赖）
draw_arrow(ax, RC[0]-RC[2]/2, RC[1]+0.2, IE[0]+IE[2]/2, IE[1]-IE[3]/2+0.5,
           style="dashed", lw=1.1, clr=EDGE_DASH)
label_at(ax, 9.3, 6.6, "依赖\n读取创新点", fs=5.5)

# 6. 关键词趋势分析器 --> 论文解析器（依赖）
draw_arrow(ax, KT[0]-KT[2]/2, KT[1]+KT[3]/2-0.2, PP[0]+PP[2]/2, PP[1]-PP[3]/2+0.2,
           style="dashed", lw=1.1, clr=EDGE_DASH)
label_at(ax, 2.6, 4.5, "依赖\n读取论文语料", fs=5.5)

# 7. 报告生成器 --> 创新点提取器（依赖）
draw_arrow(ax, RG[0]+RG[2]/2, RG[1]+0.3, IE[0]-IE[2]/2, IE[1]-IE[3]/2+0.5,
           style="dashed", lw=1.1, clr=EDGE_DASH)
label_at(ax, 3.6, 5.2, "依赖\n读取创新点", fs=5.5)

# 8. 论文解析器 --> 外部服务
draw_arrow(ax, PP[0]+PP[2]/2-0.2, PP[1]+PP[3]/2-0.2, IE[0]-1.5, IE[1]-IE[3]/2+0.5,
           style="dotted", lw=0.8, clr=EDGE_DOT)
label_at(ax, 4.8, 6.2, "外部服务\nGROBID/pdfplumber", fs=5.5)

# ── 图例 ──
leg = [
    plt.Line2D([0],[0], color=EDGE_CLR, lw=1.6, label="组合（持有实例）"),
    plt.Line2D([0],[0], color=EDGE_DASH, lw=1.1, ls="dashed", label="依赖（调用）"),
    plt.Line2D([0],[0], color=EDGE_DOT, lw=0.8, ls="dotted", label="外部服务依赖"),
]
ax.legend(handles=leg, loc="lower right", fontsize=6.5, title="关系类型", title_fontsize=7.5,
          framealpha=0.95, edgecolor=BORDER)

ax.set_title("InnoCite 系统 — 核心类图 (Class Diagram)",
             fontsize=13, fontweight="bold", pad=6, color="#1E3A5F")

ax.text(6.0, 11.9, "+ 公开方法    - 私有属性    实线箭头 = 组合    虚线箭头 = 依赖    点线箭头 = 外部服务",
        ha="center", fontsize=6.5, color="#A0AEC0")

for fmt in ["png", "svg", "pdf"]:
    path = os.path.join(OUTPUT_DIR, f"Class_Diagram.{fmt}")
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"[OK] {path}")

plt.close(fig)
print("\n[Done]")
