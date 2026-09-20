"""
PDF报告生成模块。
使用 plotly 导出图表为 PNG，reportlab 生成包含文字、图表、表格的 PDF 报告。
支持中文字体。
"""

import os
import io
import logging
import tempfile
from datetime import datetime

import plotly.graph_objects as go
import plotly.express as px
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT

from utils import BASE_DIR

logger = logging.getLogger("InnoCite.ReportGenerator")


class ReportGenerator:
    """PDF 报告生成器"""

    def __init__(self, db):
        self.db = db
        self._font_registered = False
        self._font_name = "ChineseFont"

    def _register_fonts(self):
        """注册中文字体"""
        if self._font_registered:
            return

        # 尝试多个可能的字体路径
        font_paths = [
            os.path.join(BASE_DIR, "data", "AlibabaPuHuiTi-3-55-Regular.ttf"),
            os.path.join(BASE_DIR, "data", "SimHei.ttf"),
            os.path.join(BASE_DIR, "data", "NotoSansSC-Regular.ttf"),
            os.path.join(BASE_DIR, "data", "SourceHanSansSC-Regular.otf"),
            # Windows 系统字体
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simsun.ttc",
            # macOS 系统字体
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont(self._font_name, font_path))
                    self._font_registered = True
                    return
                except Exception:
                    continue

        # 如果找不到任何中文字体，使用默认字体（中文将显示为方块）
        logger.warning("未找到中文字体，PDF中的中文可能无法正常显示。"
                       "请将中文字体文件放入 data/ 目录。")
        self._font_name = "Helvetica"
        self._font_registered = True

    def _get_styles(self):
        """获取报告样式"""
        self._register_fonts()

        styles = getSampleStyleSheet()

        # 标题样式
        styles.add(ParagraphStyle(
            "ReportTitle",
            fontName=self._font_name,
            fontSize=22,
            leading=30,
            alignment=TA_CENTER,
            spaceAfter=12,
            textColor=HexColor("#1a1a2e"),
        ))

        # 一级标题
        styles.add(ParagraphStyle(
            "H1",
            fontName=self._font_name,
            fontSize=16,
            leading=22,
            spaceBefore=16,
            spaceAfter=8,
            textColor=HexColor("#16213e"),
        ))

        # 二级标题
        styles.add(ParagraphStyle(
            "H2",
            fontName=self._font_name,
            fontSize=13,
            leading=18,
            spaceBefore=12,
            spaceAfter=6,
            textColor=HexColor("#0f3460"),
        ))

        # 正文
        styles.add(ParagraphStyle(
            "BodyCN",
            fontName=self._font_name,
            fontSize=10,
            leading=16,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        ))

        # 表格单元格
        styles.add(ParagraphStyle(
            "TableCell",
            fontName=self._font_name,
            fontSize=8,
            leading=12,
            alignment=TA_LEFT,
        ))

        # 表格头
        styles.add(ParagraphStyle(
            "TableHeader",
            fontName=self._font_name,
            fontSize=9,
            leading=13,
            alignment=TA_CENTER,
            textColor=HexColor("#ffffff"),
        ))

        # 页脚
        styles.add(ParagraphStyle(
            "Footer",
            fontName=self._font_name,
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=HexColor("#888888"),
        ))

        return styles

    def generate(self, output_path=None):
        """
        生成完整的PDF报告。
        参数:
            output_path: 输出文件路径，为None时返回 BytesIO
        返回:
            BytesIO 或文件路径
        """
        from models import Paper, Innovation

        self._register_fonts()
        styles = self._get_styles()

        # 准备数据
        papers = Paper.query.filter_by(status="success").all()
        innovations = Innovation.query.all()
        paper_count = len(papers)
        years = sorted(set(p.year for p in papers if p.year))
        year_range = f"{min(years)} - {max(years)}" if years else "N/A"

        # 学科分布
        from collections import Counter
        cat_counter = Counter(p.category for p in papers if p.category)
        category_count = len(cat_counter)

        # 决定输出方式
        if output_path:
            buffer = None
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=20*mm,
                leftMargin=20*mm,
                topMargin=20*mm,
                bottomMargin=20*mm,
            )
        else:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=20*mm,
                leftMargin=20*mm,
                topMargin=20*mm,
                bottomMargin=20*mm,
            )

        # 构建文档内容
        story = []
        temp_files = []  # 跟踪所有临时图片路径，确保最终统一清理

        # ─── 封面标题 ───
        story.append(Spacer(1, 30*mm))
        story.append(Paragraph("InnoCite 学术论文分析报告", styles["ReportTitle"]))
        story.append(Spacer(1, 8*mm))
        story.append(Paragraph(
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            ParagraphStyle("Subtitle", fontName=self._font_name, fontSize=10, alignment=TA_CENTER)
        ))
        story.append(Spacer(1, 15*mm))

        # ─── 1. 统计摘要 ───
        story.append(Paragraph("一、论文库概览", styles["H1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#0f3460")))
        story.append(Spacer(1, 5*mm))

        # 统计卡片（用表格模拟）
        stats_data = [
            [Paragraph("<b>论文总数</b>", styles["TableHeader"]),
             Paragraph("<b>年份范围</b>", styles["TableHeader"]),
             Paragraph("<b>学科数量</b>", styles["TableHeader"]),
             Paragraph("<b>创新点数量</b>", styles["TableHeader"])],
            [Paragraph(str(paper_count), styles["TableCell"]),
             Paragraph(year_range, styles["TableCell"]),
             Paragraph(str(category_count), styles["TableCell"]),
             Paragraph(str(len(innovations)), styles["TableCell"])],
        ]
        stats_table = Table(stats_data, colWidths=[40*mm, 40*mm, 40*mm, 40*mm])
        stats_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#0f3460")),
            ("BACKGROUND", (0, 1), (-1, 1), HexColor("#f0f4f8")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 8*mm))

        # ─── 2. 学科分布饼图 ───
        story.append(Paragraph("二、学科分布", styles["H1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#0f3460")))
        story.append(Spacer(1, 5*mm))

        if cat_counter:
            pie_path = self._generate_pie_chart(cat_counter)
            if pie_path:
                temp_files.append(pie_path)
                img = Image(pie_path, width=140*mm, height=100*mm)
                story.append(img)
                story.append(Spacer(1, 5*mm))

        # ─── 3. 关键词热度曲线 ───
        story.append(PageBreak())
        story.append(Paragraph("三、关键词热度趋势", styles["H1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#0f3460")))
        story.append(Spacer(1, 5*mm))

        from keyword_trend import KeywordTrendAnalyzer
        trend_analyzer = KeywordTrendAnalyzer(self.db)
        top_keywords = trend_analyzer.get_top_keywords(n=5)
        if top_keywords:
            trend_path = self._generate_trend_chart(trend_analyzer, [kw[0] for kw in top_keywords[:5]])
            if trend_path:
                temp_files.append(trend_path)
                img = Image(trend_path, width=160*mm, height=100*mm)
                story.append(img)
                story.append(Spacer(1, 5*mm))

            # 热度排名表
            story.append(Paragraph("热度排行 TOP 10：", styles["H2"]))
            top10 = top_keywords[:10]
            rank_data = [[
                Paragraph("<b>排名</b>", styles["TableHeader"]),
                Paragraph("<b>关键词</b>", styles["TableHeader"]),
                Paragraph("<b>平均热度</b>", styles["TableHeader"]),
            ]]
            for i, (kw, heat) in enumerate(top10, 1):
                rank_data.append([
                    Paragraph(str(i), styles["TableCell"]),
                    Paragraph(kw, styles["TableCell"]),
                    Paragraph(f"{heat:.4f}", styles["TableCell"]),
                ])
            rank_table = Table(rank_data, colWidths=[30*mm, 80*mm, 50*mm])
            rank_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#0f3460")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#f8f9fa")]),
            ]))
            story.append(rank_table)

        # ─── 4. 创新点汇总表 ───
        story.append(PageBreak())
        story.append(Paragraph("四、创新点汇总", styles["H1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#0f3460")))
        story.append(Spacer(1, 5*mm))

        if innovations:
            inno_data = [[
                Paragraph("<b>论文标题</b>", styles["TableHeader"]),
                Paragraph("<b>年份</b>", styles["TableHeader"]),
                Paragraph("<b>问题</b>", styles["TableHeader"]),
                Paragraph("<b>方法</b>", styles["TableHeader"]),
                Paragraph("<b>效果</b>", styles["TableHeader"]),
                Paragraph("<b>置信度</b>", styles["TableHeader"]),
            ]]
            for inno in innovations[:15]:  # 最多15篇
                paper = inno.paper
                inno_data.append([
                    Paragraph((paper.title or "")[:40], styles["TableCell"]),
                    Paragraph(str(paper.year or ""), styles["TableCell"]),
                    Paragraph((inno.problem or "")[:50], styles["TableCell"]),
                    Paragraph((inno.method or "")[:50], styles["TableCell"]),
                    Paragraph((inno.effect or "")[:50], styles["TableCell"]),
                    Paragraph(f"{inno.confidence:.0%}", styles["TableCell"]),
                ])
            inno_table = Table(
                inno_data,
                colWidths=[40*mm, 12*mm, 32*mm, 32*mm, 32*mm, 14*mm]
            )
            inno_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#0f3460")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#f8f9fa")]),
            ]))
            story.append(inno_table)

        # ─── 5. 推荐示例 ───
        story.append(PageBreak())
        story.append(Paragraph("五、跨学科推荐示例", styles["H1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#0f3460")))
        story.append(Spacer(1, 5*mm))

        from recommender import Recommender
        recommender = Recommender(self.db)
        # 获取第一篇论文的推荐作为示例
        first_paper = Paper.query.first()
        if first_paper:
            try:
                recs = recommender.recommend(first_paper.id, top_n=3)
            except Exception:
                recs = Recommendation.query.limit(3).all()
        else:
            recs = Recommendation.query.limit(3).all()

        if recs:
            for i, rec in enumerate(recs):
                rec_dict = rec.to_dict() if hasattr(rec, 'to_dict') else rec
                reason = rec_dict.get("reason", "")
                target_title = rec_dict.get("target_title", "")
                sim = rec_dict.get("similarity", 0)

                story.append(Paragraph(
                    f"<b>推荐 {i+1}</b>：{target_title[:60]}",
                    styles["H2"]
                ))
                story.append(Paragraph(
                    f"相似度：{sim:.4f} | 学科：{rec_dict.get('target_category', 'N/A')}",
                    styles["BodyCN"]
                ))
                story.append(Paragraph(f"推荐理由：{reason}", styles["BodyCN"]))
                story.append(Spacer(1, 3*mm))

        # ─── 页脚（文档末尾的文字脚注，区别于逐页页码）───
        story.append(Spacer(1, 10*mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#cccccc")))
        story.append(Paragraph("InnoCite - 学术论文创新点提炼与跨学科推荐系统", styles["Footer"]))

        # ── 页码回调函数 ──
        def _add_page_number(canvas, doc):
            """在每页底部居中绘制页码。"""
            canvas.saveState()
            canvas.setFont(self._font_name, 8)
            canvas.setFillColor(HexColor("#888888"))
            canvas.drawCentredString(
                A4[0] / 2, 12 * mm,
                f"— {doc.page} —"
            )
            canvas.restoreState()

        # 构建PDF（带逐页页码）
        try:
            doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
        finally:
            # 确保临时图表文件被清理，避免磁盘泄漏
            for tmp_path in temp_files:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        if buffer:
            buffer.seek(0)
            return buffer
        return output_path

    def _generate_pie_chart(self, cat_counter):
        """生成学科分布饼图并保存为临时PNG"""
        try:
            labels = list(cat_counter.keys())
            values = list(cat_counter.values())

            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                hole=0.3,
                marker=dict(
                    colors=["#0f3460", "#16213e", "#e94560", "#533483", "#00b4d8"]
                ),
            )])
            fig.update_layout(
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(size=11),
                showlegend=True,
                legend=dict(x=0.9, y=0.5),
            )

            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            fig.write_image(tmp.name, format="png", width=800, height=500)
            tmp.close()
            return tmp.name
        except Exception as e:
            logger.warning("饼图生成失败: %s", e)
            return None

    def _generate_trend_chart(self, trend_analyzer, keywords):
        """生成关键词热度曲线图"""
        try:
            trend_data = trend_analyzer.get_trend_data(keywords)

            fig = go.Figure()
            colors = ["#0f3460", "#e94560", "#533483", "#00b4d8", "#ff6b6b"]

            for i, series in enumerate(trend_data):
                fig.add_trace(go.Scatter(
                    x=series["x"],
                    y=series["y"],
                    mode="lines+markers",
                    name=series["keyword"],
                    line=dict(color=colors[i % len(colors)], width=2),
                    marker=dict(size=6),
                ))

            fig.update_layout(
                xaxis_title="年份",
                yaxis_title="热度值",
                yaxis_range=[0, 1],
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(size=11),
                legend=dict(x=0.02, y=0.98),
                hovermode="x unified",
            )

            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            fig.write_image(tmp.name, format="png", width=1000, height=500)
            tmp.close()
            return tmp.name
        except Exception as e:
            logger.warning("曲线图生成失败: %s", e)
            return None
