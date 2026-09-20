# -*- coding: utf-8 -*-
"""使用 Graphviz 生成 InnoCite 系统实体关系图 (E-R图) — 中文版"""

import graphviz
import os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

dot_source = u'''
digraph InnoCite_ER {
    rankdir=LR;
    dpi=150;
    fontname="Microsoft YaHei";
    fontsize=16;
    label="InnoCite 系统 — 实体关系图 (E-R 图)\\n";
    labelloc=t;

    node [shape=record, style="filled", fontname="Microsoft YaHei", fontsize=9];
    edge [fontname="Microsoft YaHei", fontsize=8];

    // ═══════════════════════ 实体定义 ═══════════════════════

    Paper [label=<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" BGCOLOR="#FFF8DC">
  <TR><TD BGCOLOR="#DAA520"><B><FONT COLOR="white">论文 (Paper)</FONT></B></TD></TR>
  <TR><TD ALIGN="LEFT"><B><U>编号</U></B> (主码) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT">arXiv编号 : VARCHAR(50)</TD></TR>
  <TR><TD ALIGN="LEFT">标题 : TEXT</TD></TR>
  <TR><TD ALIGN="LEFT">作者 : TEXT</TD></TR>
  <TR><TD ALIGN="LEFT">年份 : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT">发表场合 : VARCHAR(255)</TD></TR>
  <TR><TD ALIGN="LEFT">摘要 : TEXT</TD></TR>
  <TR><TD ALIGN="LEFT">全文 : TEXT</TD></TR>
  <TR><TD ALIGN="LEFT">学科分类 : VARCHAR(100)</TD></TR>
  <TR><TD ALIGN="LEFT">来源类型 : VARCHAR(20)</TD></TR>
  <TR><TD ALIGN="LEFT">状态 : VARCHAR(20)</TD></TR>
  <TR><TD ALIGN="LEFT">创建时间 : DATETIME</TD></TR>
</TABLE>>, fillcolor="#FFF8DC"];

    Innovation [label=<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" BGCOLOR="#F0F8FF">
  <TR><TD BGCOLOR="#4682B4"><B><FONT COLOR="white">创新点 (Innovation)</FONT></B></TD></TR>
  <TR><TD ALIGN="LEFT"><B><U>编号</U></B> (主码) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT"><B><U>论文编号</U></B> (外码, 唯一) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT">解决的问题 : TEXT</TD></TR>
  <TR><TD ALIGN="LEFT">采用的方法 : TEXT</TD></TR>
  <TR><TD ALIGN="LEFT">达到的效果 : TEXT</TD></TR>
  <TR><TD ALIGN="LEFT">完整陈述 : TEXT</TD></TR>
  <TR><TD ALIGN="LEFT">置信度 : FLOAT</TD></TR>
  <TR><TD ALIGN="LEFT">是否已确认 : BOOLEAN</TD></TR>
  <TR><TD ALIGN="LEFT">更新时间 : DATETIME</TD></TR>
</TABLE>>, fillcolor="#F0F8FF"];

    PaperEmbedding [label=<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" BGCOLOR="#F5FFFA">
  <TR><TD BGCOLOR="#3CB371"><B><FONT COLOR="white">向量嵌入 (PaperEmbedding)</FONT></B></TD></TR>
  <TR><TD ALIGN="LEFT"><B><U>编号</U></B> (主码) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT"><B><U>论文编号</U></B> (外码, 唯一) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT">向量数据 (384维) : BLOB</TD></TR>
  <TR><TD ALIGN="LEFT">创建时间 : DATETIME</TD></TR>
</TABLE>>, fillcolor="#F5FFFA"];

    Recommendation [label=<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" BGCOLOR="#FFF0F5">
  <TR><TD BGCOLOR="#DB7093"><B><FONT COLOR="white">推荐结果 (Recommendation)</FONT></B></TD></TR>
  <TR><TD ALIGN="LEFT"><B><U>编号</U></B> (主码) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT"><B>源论文编号</B> (外码) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT"><B>目标论文编号</B> (外码) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT">相似度 : FLOAT</TD></TR>
  <TR><TD ALIGN="LEFT">推荐理由 : TEXT</TD></TR>
  <TR><TD ALIGN="LEFT">创建时间 : DATETIME</TD></TR>
</TABLE>>, fillcolor="#FFF0F5"];

    User [label=<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" BGCOLOR="#FFF5EE">
  <TR><TD BGCOLOR="#CD853F"><B><FONT COLOR="white">用户 (User)</FONT></B></TD></TR>
  <TR><TD ALIGN="LEFT"><B><U>编号</U></B> (主码) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT">用户名 : VARCHAR(64)</TD></TR>
  <TR><TD ALIGN="LEFT">密码哈希 : VARCHAR(128)</TD></TR>
  <TR><TD ALIGN="LEFT">显示名称 : VARCHAR(64)</TD></TR>
  <TR><TD ALIGN="LEFT">是否激活 : BOOLEAN</TD></TR>
  <TR><TD ALIGN="LEFT">创建时间 : DATETIME</TD></TR>
</TABLE>>, fillcolor="#FFF5EE"];

    KeywordCache [label=<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" BGCOLOR="#F0FFF0">
  <TR><TD BGCOLOR="#6B8E23"><B><FONT COLOR="white">关键词缓存 (KeywordCache)</FONT></B></TD></TR>
  <TR><TD ALIGN="LEFT"><B><U>编号</U></B> (主码) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT">缓存键 : VARCHAR(64)</TD></TR>
  <TR><TD ALIGN="LEFT">缓存数据 : JSON</TD></TR>
  <TR><TD ALIGN="LEFT">论文数量 : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT">配置版本号 : VARCHAR(32)</TD></TR>
  <TR><TD ALIGN="LEFT">更新时间 : DATETIME</TD></TR>
</TABLE>>, fillcolor="#F0FFF0"];

    user_bookmarks [label=<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" BGCOLOR="#FAFAD2">
  <TR><TD BGCOLOR="#BDB76B"><B>收藏关联 (user_bookmarks)</B></TD></TR>
  <TR><TD ALIGN="LEFT"><B><U>用户编号</U></B> (外码, 主码) : INTEGER</TD></TR>
  <TR><TD ALIGN="LEFT"><B><U>论文编号</U></B> (外码, 主码) : INTEGER</TD></TR>
</TABLE>>, fillcolor="#FAFAD2"];

    // ═══════════════════════ 关系连线 ═══════════════════════

    Paper -> Innovation [
        label="1 : 1    拥有",
        color="#4682B4", penwidth=2,
        arrowhead=none, arrowtail=none,
        headlabel=" 1", taillabel="1 ",
        fontcolor="#4682B4", fontsize=9
    ];

    Paper -> PaperEmbedding [
        label="1 : 1    拥有",
        color="#3CB371", penwidth=2,
        arrowhead=none, arrowtail=none,
        headlabel=" 1", taillabel="1 ",
        fontcolor="#3CB371", fontsize=9
    ];

    Paper -> Recommendation [
        label="1 : N    作为源论文",
        color="#DB7093", penwidth=1.5,
        arrowhead=crow, arrowtail=none,
        headlabel=" N", taillabel="1 ",
        fontcolor="#DB7093", fontsize=8
    ];

    Recommendation -> Paper [
        label="N : 1    作为目标论文",
        color="#DB7093", penwidth=1.5, style=dashed,
        arrowhead=none, arrowtail=crow,
        headlabel=" 1", taillabel="N ",
        fontcolor="#DB7093", fontsize=8
    ];

    User -> user_bookmarks [
        label="1 : N    收藏记录",
        color="#BDB76B", penwidth=1.5,
        arrowhead=crow, arrowtail=none,
        headlabel=" N", taillabel="1 ",
        fontcolor="#BDB76B", fontsize=8
    ];

    Paper -> user_bookmarks [
        label="1 : N    被收藏",
        color="#BDB76B", penwidth=1.5,
        arrowhead=crow, arrowtail=none,
        headlabel=" N", taillabel="1 ",
        fontcolor="#BDB76B", fontsize=8
    ];

    Paper -> KeywordCache [
        label="   事件触发器同步",
        color="#6B8E23", penwidth=1.2, style=dotted,
        arrowhead=none, arrowtail=none,
        fontcolor="#6B8E23", fontsize=7
    ];

    // ═══════════════════════ 图例 ═══════════════════════
    subgraph cluster_legend {
        label="图 例";
        fontsize=11;
        fontname="Microsoft YaHei";
        style="rounded,dashed";
        color=gray50;
        bgcolor=ghostwhite;

        leg1 [shape=plaintext, fontsize=8, fontname="Microsoft YaHei",
              label="主码 = 主键 (Primary Key)  |  外码 = 外键 (Foreign Key)  |  唯一 = 唯一约束"];
        leg2 [shape=plaintext, fontsize=8, fontname="Microsoft YaHei",
              label="实线 = 强实体关系  |  虚线 = 反向引用  |  点线 = 事件触发同步"];
        leg3 [shape=plaintext, fontsize=8, fontname="Microsoft YaHei",
              label="1:1 = 一对一  |  1:N = 一对多  |  M:N 多对多（通过收藏关联表实现）"];
    }
}
'''

# 写入 DOT 文件
dot_path = os.path.join(OUTPUT_DIR, "ER_Diagram_CN.dot")
with open(dot_path, "w", encoding="utf-8") as f:
    f.write(dot_source)

# 渲染
for fmt in ["png", "svg"]:
    try:
        graphviz.render(engine="dot", format=fmt, filepath=dot_path)
        output_path = os.path.join(OUTPUT_DIR, f"ER_Diagram_CN.{fmt}")
        print(f"[OK] Generated: {output_path}")
    except Exception as e:
        print(f"[Skip] {fmt}: {e}")

print("\n[Done] Graphviz Chinese ER Diagram generated!")
print(f"      Output directory: {OUTPUT_DIR}")
