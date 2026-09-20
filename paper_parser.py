"""
论文导入与解析模块。
支持: arXiv ID导入、arXiv关键词搜索、CSV导入、PDF上传解析。

PDF 解析采用双轨策略：
  1. GROBID（优先）— 机器学习驱动的学术 PDF 元数据提取
  2. pdfplumber（回退）— 基于规则的本地解析
"""

import os
import re
import time
import logging
import tempfile
from datetime import datetime

import arxiv
import pdfplumber

from models import db, Paper
from utils import BASE_DIR

logger = logging.getLogger("InnoCite.PaperParser")


class PaperParser:
    """论文解析器：处理不同来源的论文导入"""

    # arXiv分类映射（用于补充缺失分类）
    CATEGORY_PATTERNS = {
        "cs.CV": ["computer vision", "image", "visual", "object detection", "segmentation"],
        "cs.CL": ["language", "nlp", "text", "translation", "speech"],
        "cs.AI": ["machine learning", "neural network", "reinforcement", "deep learning"],
        "cs.LG": ["learning", "gradient", "optimization", "generalization"],
        "cs.IR": ["information retrieval", "search", "ranking"],
        "stat.ML": ["statistical", "bayesian", "inference"],
    }

    def import_arxiv_by_id(self, arxiv_id):
        """
        通过 arXiv ID 导入单篇论文。
        返回: (success: bool, message: str, paper: Paper or None)
        """
        # 清理ID格式
        arxiv_id = arxiv_id.strip()
        # 移除URL前缀
        arxiv_id = re.sub(r'https?://arxiv\.org/abs/', '', arxiv_id)
        arxiv_id = re.sub(r'https?://arxiv\.org/pdf/', '', arxiv_id)
        arxiv_id = re.sub(r'\.pdf$', '', arxiv_id)

        try:
            # 检查是否已存在
            existing = Paper.query.filter_by(arxiv_id=arxiv_id).first()
            if existing:
                return True, "该论文已存在于数据库中", existing

            # 调用 arXiv API（arxiv 4.x: client.results(search)）
            search = arxiv.Search(id_list=[arxiv_id])
            client = arxiv.Client()
            result = next(client.results(search), None)

            if result is None:
                return False, f"未找到 arXiv ID: {arxiv_id} 的论文", None

            paper = self._arxiv_result_to_paper(result)
            db.session.add(paper)
            db.session.commit()

            return True, f"成功导入: {paper.title[:60]}...", paper

        except Exception as e:
            db.session.rollback()
            return False, f"导入失败: {str(e)}", None

    def search_arxiv(self, query, max_results=50, year_from=None, year_to=None):
        """
        通过关键词搜索 arXiv 导入论文。
        参数:
            query: 搜索关键词
            max_results: 最大结果数
            year_from: 起始年份
            year_to: 结束年份
        返回: (success: bool, message: str, imported_count: int, papers: list)
        """
        try:
            # 构建搜索查询（年份过滤直接写入查询语句，避免浪费 API 额度）
            search_query = query

            if year_from or year_to:
                from_date = f"{year_from}01010000" if year_from else "000001010000"
                to_date = f"{year_to}12312359" if year_to else "999912312359"
                search_query += f" AND submittedDate:[{from_date} TO {to_date}]"

            client = arxiv.Client()

            # 构建高级搜索
            search = arxiv.Search(
                query=search_query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )

            imported = []
            failed = []

            for result in client.results(search):
                try:
                    paper = self._arxiv_result_to_paper(result)

                    # 检查是否已存在（按arxiv_id）
                    if paper.arxiv_id:
                        existing = Paper.query.filter_by(arxiv_id=paper.arxiv_id).first()
                        if existing:
                            imported.append(existing)
                            continue

                    # 检查是否已存在（按标题去重）
                    existing = Paper.query.filter_by(title=paper.title).first()
                    if existing:
                        imported.append(existing)
                        continue

                    db.session.add(paper)
                    db.session.flush()
                    imported.append(paper)

                except Exception as e:
                    failed.append({"title": result.title, "error": str(e)})
                    continue

                # 礼貌地延迟以避免API限速
                time.sleep(0.1)

            db.session.commit()

            msg = f"成功导入 {len(imported)} 篇论文"
            if failed:
                msg += f"，{len(failed)} 篇失败"

            return True, msg, len(imported), imported

        except Exception as e:
            db.session.rollback()
            return False, f"搜索失败: {str(e)}", 0, []

    def import_csv(self, file_path):
        """
        从 CSV 文件导入论文。
        CSV 列: title, authors, year, abstract, category (可选: arxiv_id, venue)
        返回: (success: bool, message: str, imported_count: int)
        """
        import csv

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                return False, "CSV 文件为空或无有效数据行", 0

            imported = 0
            failed = 0

            for i, row in enumerate(rows):
                try:
                    title = row.get("title", "").strip()
                    if not title:
                        failed += 1
                        continue

                    # 解析年份
                    year = None
                    year_str = row.get("year", "").strip()
                    if year_str:
                        try:
                            year = int(year_str)
                        except ValueError:
                            year = None

                    paper = Paper(
                        arxiv_id=row.get("arxiv_id", "").strip() or None,
                        title=title,
                        authors=row.get("authors", "").strip(),
                        year=year,
                        venue=row.get("venue", "").strip() or None,
                        abstract=row.get("abstract", "").strip(),
                        category=row.get("category", "").strip() or self._guess_category(title, row.get("abstract", "")),
                        source_type="CSV",
                        status="success",
                    )

                    # 去重检查
                    existing = Paper.query.filter_by(title=paper.title).first()
                    if existing:
                        failed += 1
                        continue

                    db.session.add(paper)
                    imported += 1

                except Exception as e:
                    failed += 1
                    continue

            db.session.commit()
            return True, f"成功导入 {imported} 篇，{failed} 篇失败或重复", imported

        except Exception as e:
            db.session.rollback()
            return False, f"CSV 解析失败: {str(e)}", 0

    def import_pdf(self, file_path):
        """
        从 PDF 文件提取论文元数据。
        返回: (success: bool, message: str, paper: Paper or None)
        """
        try:
            metadata = self._extract_pdf_metadata(file_path)

            if not metadata.get("title"):
                return False, "无法从PDF中提取标题，请手动填写", None

            paper = Paper(
                title=metadata.get("title", "未知标题"),
                authors=metadata.get("authors", ""),
                year=metadata.get("year"),
                abstract=metadata.get("abstract", ""),
                full_text=metadata.get("full_text", ""),
                category=metadata.get("category") or self._guess_category(
                    metadata.get("title", ""), metadata.get("abstract", "")
                ),
                source_type="PDF",
                status="success" if metadata.get("title") else "failed",
            )

            db.session.add(paper)
            db.session.commit()

            return True, f"PDF解析成功: {paper.title[:60]}...", paper

        except Exception as e:
            return False, f"PDF解析失败: {str(e)}", None

    def _extract_pdf_metadata(self, file_path):
        """从PDF提取标题、作者、摘要、全文。

        双轨策略：GROBID（机器学习）→ pdfplumber（本地规则）逐级回退。
        """
        from config import get_config

        # ── 策略 0：GROBID（如果可用）──
        config = get_config()
        if config.GROBID_ENABLED:
            from grobid_client import extract_header, is_available
            try:
                if is_available(config.GROBID_URL, timeout=3):
                    logger.info("使用 GROBID 解析 PDF…")
                    grobid_meta = extract_header(
                        file_path,
                        grobid_url=config.GROBID_URL,
                        timeout=config.GROBID_TIMEOUT,
                    )
                    if grobid_meta and grobid_meta.get("title"):
                        # 补齐 full_text（GROBID 可能也返回摘要，如果没有再走 pdfplumber）
                        pdfplumber_meta = self._parse_with_pdfplumber(file_path)
                        grobid_meta["full_text"] = pdfplumber_meta.get("full_text", "")
                        grobid_meta.setdefault("abstract", pdfplumber_meta.get("abstract"))
                        grobid_meta.setdefault("category", None)
                        logger.info(
                            "GROBID 解析成功: 标题=%s, 作者=%d 位",
                            (grobid_meta.get("title") or "")[:50],
                            len((grobid_meta.get("authors") or "").split(";")),
                        )
                        return grobid_meta
                    else:
                        logger.info("GROBID 未能提取有效标题，回退到 pdfplumber")
                else:
                    logger.info("GROBID 服务不在线，回退到 pdfplumber")
            except Exception:
                logger.warning("GROBID 调用异常，回退到 pdfplumber", exc_info=True)

        return self._parse_with_pdfplumber(file_path)

    def _parse_with_pdfplumber(self, file_path):
        """pdfplumber 本地解析（原有逻辑）。"""
        metadata = {
            "title": None,
            "authors": None,
            "year": None,
            "abstract": None,
            "full_text": "",
            "category": None,
        }

        try:
            with pdfplumber.open(file_path) as pdf:
                # ── 1. 提取全文文本（前20页）──
                all_text = []
                for page in pdf.pages[:20]:
                    text = page.extract_text()
                    if text:
                        all_text.append(text)

                full_text = "\n".join(all_text)
                metadata["full_text"] = full_text

                if not full_text.strip():
                    return metadata

                # ── 2. PDF 内置元数据 ──
                pdf_meta = pdf.metadata or {}
                meta_title = (pdf_meta.get("Title") or "").strip()
                meta_author = (pdf_meta.get("Author") or "").strip()

                # 过滤无效元数据（有时是文件名或无意义字符串）
                if meta_title and len(meta_title) > 5 and not meta_title.endswith((".pdf", ".tex")):
                    metadata["title"] = self._clean_title(meta_title)

                if meta_author and len(meta_author) > 2 and meta_author.lower() not in ("unknown", "author"):
                    metadata["authors"] = self._clean_authors(meta_author)

                # ── 3. 字体大小分析提取标题 ──
                if not metadata["title"] and pdf.pages:
                    font_title = self._extract_title_by_font_size(pdf.pages[0])
                    if font_title:
                        metadata["title"] = self._clean_title(font_title)

                # ── 4. 位置启发式（标题回退）──
                if not metadata["title"] and pdf.pages:
                    pos_title = self._extract_title_by_position(pdf.pages[0])
                    if pos_title:
                        metadata["title"] = self._clean_title(pos_title)

                # ── 5. 多模式摘要提取 ──
                metadata["abstract"] = self._extract_abstract_multi_pattern(full_text)

                # ── 6. 作者提取（回退）──
                if not metadata["authors"]:
                    metadata["authors"] = self._extract_authors_from_text(full_text)

                # ── 7. 年份提取（多模式）──
                metadata["year"] = self._extract_year_multi_pattern(full_text, pdf_meta)

                # ── 8. DOI / arXiv ID 提取 ──
                arxiv_match = re.search(r'arXiv:(\d+\.\d+(?:v\d+)?)', full_text, re.IGNORECASE)
                if arxiv_match:
                    metadata["arxiv_id"] = arxiv_match.group(1)

                doi_match = re.search(
                    r'(?:doi[:\s]*|DOI[:\s]*)?(10\.\d{4,}/[^\s"\']+)',
                    full_text, re.IGNORECASE
                )
                if doi_match:
                    metadata["doi"] = doi_match.group(1)

                pdf.close()

        except Exception as e:
            metadata["full_text"] = f"[PDF解析错误: {e}]"

        return metadata

    # ═══════════════════════════════════════════════
    # 标题提取子策略
    # ═══════════════════════════════════════════════

    def _extract_title_by_font_size(self, first_page):
        """通过字体大小分析提取标题（最大字体的文本行通常是标题）"""
        try:
            chars = first_page.chars
            if not chars:
                return None

            # 按字符的 y 坐标和字号分组
            from collections import defaultdict
            line_groups = defaultdict(list)
            for c in chars:
                # 同一行的字符（y 坐标相近）
                y_key = round(c.get("top", 0), 0)
                line_groups[y_key].append(c)

            # 找到每行中最大的字号
            line_max_font = {}
            for y, group in line_groups.items():
                max_size = max(c.get("height", 0) for c in group if c.get("height"))
                text = "".join(c.get("text", "") for c in sorted(group, key=lambda x: x.get("x0", 0)))
                line_max_font[y] = (max_size, text.strip())

            # 取字号最大的行（排除页眉页脚 — 通常在最顶部或最底部）
            sorted_lines = sorted(
                [(y, size, text) for y, (size, text) in line_max_font.items()],
                key=lambda x: x[1], reverse=True
            )

            if sorted_lines:
                page_height = first_page.height or 800
                for y, size, text in sorted_lines:
                    # 跳过页眉（顶部 15%）和页脚（底部 15%）
                    if y < page_height * 0.15 or y > page_height * 0.85:
                        continue
                    # 跳过明显不是标题的行（太短、包含 arXiv、纯数字）
                    if len(text) < 8:
                        continue
                    if re.match(r'^(arXiv|\d+[\d\s,]*)$', text, re.IGNORECASE):
                        continue
                    return text

            # 放宽条件：取字号最大的行
            best = sorted_lines[0]
            return best[2] if len(best[2]) > 5 else None

        except Exception:
            logger.debug("字体大小标题提取失败（将尝试下一策略）", exc_info=True)
            return None

    def _extract_title_by_position(self, first_page):
        """位置启发式提取标题（前几行非空、非元数据文本）"""
        try:
            text = first_page.extract_text() or ""
            lines = text.split("\n")

            candidates = []
            for i, line in enumerate(lines[:15]):
                line = line.strip()
                if not line:
                    continue
                # 跳过明显的元数据行
                if any(skip in line.lower() for skip in [
                    "arxiv", "doi:", "http", "copyright", "©", "published",
                    "proceedings", "conference", "journal", "volume", "vol.",
                ]):
                    continue
                # 标题行特征：较长的纯文字行，没有过多的标点/数字
                if 15 < len(line) < 350:
                    letters = sum(1 for c in line if c.isalpha() or c.isspace())
                    ratio = letters / max(len(line), 1)
                    if ratio > 0.65:  # 至少 65% 是字母/空格
                        candidates.append((i, line))

            if candidates:
                # 取最早出现的合格行
                candidates.sort(key=lambda x: x[0])
                return candidates[0][1]
            return None
        except Exception:
            logger.debug("位置启发式标题提取失败（将尝试下一策略）", exc_info=True)
            return None

    @staticmethod
    def _clean_title(title):
        """清理标题文本"""
        title = title.strip()
        # 去除前缀编号
        title = re.sub(r'^[\d\s.]+', '', title)
        # 去除末尾的标点
        title = title.rstrip('.,;:-')
        # 合并多余空白
        title = re.sub(r'\s+', ' ', title)
        return title[:350] if len(title) > 350 else title

    # ═══════════════════════════════════════════════
    # 摘要提取
    # ═══════════════════════════════════════════════

    def _extract_abstract_multi_pattern(self, full_text):
        """多模式摘要提取，按优先级尝试"""
        patterns = [
            # 模式1：标准 "Abstract" 标题 + 段落分隔
            (r'(?i)abstract[:\s\-]*\n{1,3}(.+?)(?:\n{2,}|(?:\n\s*(?:\d+\.?\s*)?(?:Introduction|1\.?\s|I\.\s)))',
             "标准英文摘要"),
            # 模式2：中文"摘要"标题
            (r'摘\s*要[：:\s\-]*\n{1,3}(.+?)(?:\n{2,}|(?:\n\s*(?:\d+\.?\s*)?(?:引言|前言|1\.?\s|一、)))',
             "中文摘要"),
            # 模式3：弱分隔（直到空行结束）
            (r'(?i)(?:abstract|摘要)[:\s\-]*\n{0,2}(.+?)(?:\n\s*\n)',
             "弱分隔摘要"),
            # 模式4：无标题标记 — 取 "Abstract" 后固定字符数
            (r'(?i)abstract[:\s\-]?(.{100,2500})',
             "宽松匹配"),
        ]

        for pattern, desc in patterns:
            match = re.search(pattern, full_text, re.DOTALL)
            if match:
                abstract = match.group(1).strip()
                # 过滤太短或明显不是摘要的内容
                if len(abstract) > 30 and not abstract.startswith(("http", "doi:")):
                    # 清理行内换行和多余空白
                    abstract = re.sub(r'(?<!\n)\n(?!\n)', ' ', abstract)
                    abstract = re.sub(r'\s+', ' ', abstract)
                    return abstract[:3000]

        return None

    # ═══════════════════════════════════════════════
    # 作者提取
    # ═══════════════════════════════════════════════

    def _extract_authors_from_text(self, full_text):
        """从文本中提取作者信息"""
        # 取第一页的前 1000 字符用于作者搜索
        first_section = full_text[:1500] if len(full_text) > 1500 else full_text

        # 模式：姓, 名 或 名 姓 格式
        author_patterns = [
            # IEEE/ACM 格式：作者名后跟数字上标（机构编号）
            r'(?:^|\n)([A-Z][a-z]+(?:\s+[A-Z]\.)*\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)(?:\s*[\d,]+)*\n',
            # 多作者用分号或逗号分隔
            r'(?:authors?[:\s]*)([A-Za-z\s,;\.\-]+?)(?:\n|$)',
            # 在标题后、摘要前的文本块中寻找
            r'(?:^|\n)\s*([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*,\s*[A-Z][a-z]+\s+[A-Z][a-z]+)*)\s*\n',
        ]

        for pattern in author_patterns:
            match = re.search(pattern, first_section, re.MULTILINE)
            if match:
                authors = match.group(1).strip()
                if 5 < len(authors) < 500:
                    return self._clean_authors(authors)

        return ""

    @staticmethod
    def _clean_authors(authors):
        """清理作者字符串"""
        # 移除数字上标和多余符号
        authors = re.sub(r'[\d*†‡§¶#]+', '', authors)
        # 统一分隔符
        authors = re.sub(r'[,;](\s*)and\s', r'; ', authors, flags=re.IGNORECASE)
        authors = re.sub(r'[;,]+\s*', '; ', authors)
        # 合并多余空白
        authors = re.sub(r'\s+', ' ', authors)
        return authors.strip().rstrip(';,').strip()

    # ═══════════════════════════════════════════════
    # 年份提取
    # ═══════════════════════════════════════════════

    def _extract_year_multi_pattern(self, full_text, pdf_meta):
        """多模式年份提取"""
        # 1. PDF 元数据中的创建日期
        if pdf_meta:
            for key in ("CreationDate", "ModDate"):
                date_str = pdf_meta.get(key, "")
                if date_str:
                    match = re.search(r'(19|20)\d{2}', str(date_str))
                    if match:
                        year = int(match.group())
                        if 1990 <= year <= 2026:
                            return year

        # 2. 版权年份标记
        copyright_match = re.search(
            r'(?:©|copyright\s+|Copyright\s+)(?:©\s*)?(19\d{2}|20\d{2})',
            full_text, re.IGNORECASE
        )
        if copyright_match:
            year = int(copyright_match.group(1))
            if 1990 <= year <= 2026:
                return year

        # 3. 会议/期刊 + 年份模式
        conf_match = re.search(
            r'(?:CVPR|ICCV|ECCV|NeurIPS|ICML|ICLR|ACL|EMNLP|NAACL|AAAI|IJCAI|'
            r'SIGGRAPH|WWW|KDD|ICDM|AISTATS)\s*[\'’]?\s*(19\d{2}|20\d{2})',
            full_text
        )
        if conf_match:
            return int(conf_match.group(1))

        # 4. 发表/接受日期
        pub_match = re.search(
            r'(?:published|accepted|received)[:\s]+.*?(19\d{2}|20\d{2})',
            full_text, re.IGNORECASE
        )
        if pub_match:
            return int(pub_match.group(1))

        # 5. 任意合理的年份（取第一个）
        for m in re.finditer(r'(?<!\d)(19[5-9]\d|20[0-2]\d)(?!\d)', full_text):
            year = int(m.group())
            if 1990 <= year <= 2026:
                return year

        return None

    def _fetch_arxiv_fulltext(self, result, timeout=20):
        """抓取 arXiv 论文正文（full_text）。

        策略（逐级回退）：
          1. ar5iv HTML（https://ar5iv.labs.arxiv.org/html/）— 覆盖老论文，结构完整
          2. arXiv 原生 HTML（https://arxiv.org/html/）— 2023 年后新论文
          3. 下载 PDF → pdfplumber 本地解析

        返回正文文本（去 HTML 标签），失败返回 None（不影响导入主流程）。
        """
        paper_id = result.get_short_id()
        if not paper_id:
            return None

        import requests as _requests

        # ── 1-2. HTML 抓取 ──
        html_urls = [
            f"https://ar5iv.labs.arxiv.org/html/{paper_id}",
            f"https://arxiv.org/html/{paper_id}",
        ]
        for url in html_urls:
            try:
                resp = _requests.get(
                    url,
                    timeout=timeout,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                )
                if resp.status_code != 200:
                    continue
                text = self._html_to_plain_text(resp.text)
                # 正文有效长度阈值：过滤掉"仅摘要页"的误判
                if text and len(text) > 800:
                    logger.info("arXiv 全文获取成功(HTML): %s (%d 字符)", paper_id, len(text))
                    return text
            except Exception:
                continue

        # ── 3. PDF 下载 + 本地解析 ──
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
            result.download_pdf(tmp_path)
            meta = self._parse_with_pdfplumber(tmp_path)
            os.unlink(tmp_path)
            full_text = (meta or {}).get("full_text", "")
            if full_text and len(full_text) > 800:
                logger.info("arXiv 全文获取成功(PDF): %s (%d 字符)", paper_id, len(full_text))
                return full_text
        except Exception:
            logger.debug("arXiv 全文 PDF 抓取失败: %s", paper_id, exc_info=True)

        return None

    @staticmethod
    def _html_to_plain_text(html):
        """将 arXiv HTML 页面转换为纯文本（去脚本/样式/标签）。"""
        # 移除 script/style 块
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        # 移除所有标签
        text = re.sub(r"<[^>]+>", " ", html)
        # 解 HTML 实体
        import html as _html
        text = _html.unescape(text)
        # 压缩空白
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _arxiv_result_to_paper(self, result):
        """将 arxiv.Result 转换为 Paper 模型"""
        # 提取年份
        year = None
        if result.published:
            year = result.published.year

        # 提取一级分类
        category = None
        if result.categories:
            # 取第一个分类作为主分类
            category = result.categories[0].strip()

        # 处理作者
        authors = "; ".join([a.name for a in result.authors]) if result.authors else ""

        # 清理摘要（移除换行符）
        summary = result.summary.replace("\n", " ").strip() if result.summary else ""

        # 抓取正文（失败不影响导入，full_text 保持 None）
        full_text = None
        try:
            full_text = self._fetch_arxiv_fulltext(result)
        except Exception:
            logger.debug("arXiv 正文抓取失败（不影响导入）: %s", result.get_short_id(), exc_info=True)

        paper = Paper(
            arxiv_id=result.get_short_id(),
            title=result.title.strip(),
            authors=authors,
            year=year,
            venue=result.journal_ref or None,
            abstract=summary,
            full_text=full_text,
            category=category,
            source_type="arXiv",
            status="success",
        )

        return paper

    def _guess_category(self, title, abstract):
        """根据标题和摘要推测学科分类。

        优先使用 SBERT/LLM 语义分类，不可用时回退到关键词规则。
        """
        # ── 路径 1：语义分类 ──
        import os
        if os.environ.get("AUTO_CLASSIFY_ENABLED", "1") == "1":
            try:
                from paper_classifier import get_classifier
                classifier = get_classifier()
                result = classifier.classify(title, abstract)
                if result:
                    logger.info("论文学科由语义分类确定: %s", result)
                    return result
            except Exception:
                logger.debug("语义分类不可用，回退到关键词规则", exc_info=True)

        # ── 路径 2：关键词规则回退 ──
        text = (title + " " + (abstract or "")).lower()
        max_score = 0
        best_category = None

        for category, keywords in self.CATEGORY_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > max_score:
                max_score = score
                best_category = category

        return best_category if max_score > 0 else "unknown"

    def get_csv_template(self):
        """生成CSV模板内容"""
        headers = ["title", "authors", "year", "abstract", "category", "arxiv_id", "venue"]
        example = [
            "Deep Learning for Image Classification",
            "John Smith; Jane Doe",
            "2023",
            "This paper presents a novel approach to image classification using deep convolutional networks...",
            "cs.CV",
            "2301.00123",
            "CVPR 2023",
        ]
        return ",".join(headers) + "\n" + ",".join(example)

    def import_enw(self, file_path):
        """
        从 EndNote (.enw) 文件导入论文（知网/万方导出格式兼容）。
        返回: (success: bool, message: str, imported_count: int)
        """
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            # .enw 文件以 "  "（两个空格）或 "\n\n" 分隔多条记录
            # 处理两种分隔方式
            raw_records = re.split(r'\n\s*\n(?=%)', content.strip())
            if len(raw_records) == 1:
                # 可能没有空行分隔，尝试按 %0 拆分
                raw_records = re.split(r'\n(?=%0 )', content.strip())

            imported = 0
            failed = 0

            for record in raw_records:
                record = record.strip()
                if not record or not record.startswith("%"):
                    continue

                try:
                    paper_data = self._parse_enw_record(record)
                    if not paper_data.get("title"):
                        failed += 1
                        continue

                    # 去重检查
                    existing = Paper.query.filter_by(title=paper_data["title"]).first()
                    if existing:
                        continue

                    paper = Paper(
                        title=paper_data["title"],
                        authors=paper_data.get("authors", ""),
                        year=paper_data.get("year"),
                        venue=paper_data.get("venue", ""),
                        abstract=paper_data.get("abstract", ""),
                        category=paper_data.get("category")
                        or self._guess_category(
                            paper_data["title"], paper_data.get("abstract", "")
                        ),
                        source_type="EndNote",
                        status="success",
                    )
                    db.session.add(paper)
                    imported += 1

                except Exception:
                    failed += 1
                    continue

            db.session.commit()
            return True, f"成功导入 {imported} 篇，{failed} 篇失败或重复", imported

        except Exception as e:
            db.session.rollback()
            return False, f"ENW 解析失败: {str(e)}", 0

    def _parse_enw_record(self, record):
        """解析单条 EndNote 记录，返回 dict。

        EndNote 标签格式：
            %0 文献类型    %A 作者（可多行）  %T 标题
            %J 期刊/会议名  %D 年份          %X 摘要
            %K 关键词      %B 书名/来源      %U URL
        """
        data = {
            "title": None,
            "authors": None,
            "year": None,
            "venue": None,
            "abstract": None,
            "category": None,
        }
        authors = []

        for line in record.split("\n"):
            line = line.strip()
            if len(line) < 3:
                continue

            tag = line[:2]
            value = line[3:].strip()

            if tag == "%T" and not data["title"]:
                data["title"] = value[:500]
            elif tag == "%A":
                # 清理作者名（去除机构编号、邮箱等）
                cleaned = re.sub(r'\s*\([^)]*\)', '', value)  # 去括号内容
                cleaned = re.sub(r'[\d*†‡§¶#@]+', '', cleaned)  # 去数字符号
                cleaned = cleaned.strip().rstrip(',;')
                if cleaned and len(cleaned) > 1:
                    authors.append(cleaned)
            elif tag == "%D":
                # 年份可能包含完整日期，提取年份部分
                year_match = re.search(r'(19\d{2}|20\d{2})', value)
                if year_match and not data["year"]:
                    data["year"] = int(year_match.group(1))
            elif tag == "%J" or tag == "%B":
                if not data["venue"]:
                    data["venue"] = value[:255]
            elif tag == "%X":
                if not data["abstract"]:
                    data["abstract"] = value[:5000]
            elif tag == "%K":
                # 关键词可以辅助分类推测
                if not data["category"]:
                    data["category"] = self._guess_category(
                        data["title"] or "", value
                    )

        if authors:
            data["authors"] = "; ".join(authors)

        return data

    def import_bibtex(self, file_path):
        """
        从 BibTeX (.bib) 文件导入论文（支持 Google Scholar / DBLP / ACM 导出格式）。

        返回: (success: bool, message: str, imported_count: int)
        """
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            # 使用简单的正则解析 BibTeX（不依赖 bibtexparser 库，降低依赖）
            entries = self._parse_bibtex_entries(content.encode("utf-8"))
            if not entries:
                return False, "BibTeX 文件中未找到有效条目", 0

            imported = 0
            failed = 0

            for entry_data in entries:
                title = entry_data.get("title", "").strip().strip("{}")
                if not title:
                    failed += 1
                    continue

                # 去重
                existing = Paper.query.filter_by(title=title).first()
                if existing:
                    continue

                try:
                    year_val = None
                    year_str = entry_data.get("year", "").strip().strip("{}")
                    if year_str and year_str.isdigit():
                        year_val = int(year_str)

                    authors = entry_data.get("author", "")
                    # 统一 " and " 分隔符
                    authors = re.sub(r"\s+and\s+", "; ", authors.strip().strip("{}"))

                    paper = Paper(
                        title=title[:500],
                        authors=authors[:500],
                        year=year_val,
                        venue=(entry_data.get("journal") or entry_data.get("booktitle") or "").strip().strip("{}")[:255],
                        abstract=(entry_data.get("abstract") or "").strip().strip("{}")[:5000],
                        category=self._guess_category(
                            title,
                            entry_data.get("abstract", ""),
                        ),
                        source_type="BibTeX",
                        status="success",
                    )
                    db.session.add(paper)
                    imported += 1

                except Exception:
                    failed += 1
                    continue

            db.session.commit()
            return True, f"成功导入 {imported} 篇，{failed} 篇失败或重复", imported

        except Exception as e:
            db.session.rollback()
            return False, f"BibTeX 解析失败: {str(e)}", 0

    @staticmethod
    def _parse_bibtex_entries(raw_bytes):
        """简易 BibTeX 解析器（不依赖外部库）。

        逐条解析 @article{...} 和 @inproceedings{...} 条目，
        支持跨行字段值。
        返回 list of dict。
        """
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw_bytes.decode("latin-1")

        entries = []
        # 匹配 @type{key, ...} 结构
        pattern = re.compile(
            r'@(\w+)\s*\{\s*([^,]+)\s*,\s*(.+?)\n\}',
            re.DOTALL | re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            entry_type = match.group(1).lower()
            if entry_type not in ("article", "inproceedings", "incollection",
                                  "proceedings", "book", "techreport", "misc"):
                continue

            body = match.group(3)
            data = {}
            # 逐行解析 field = {value} 或 field = "value"
            for field_match in re.finditer(
                r'(\w+)\s*=\s*[{"]([^}"]*(?:\{[^}]*\}[^}"]*)*)[}"]\s*,?',
                body, re.DOTALL,
            ):
                field_name = field_match.group(1).lower()
                field_value = field_match.group(2).strip()
                # 清理嵌套花括号
                field_value = re.sub(r'\{|\}', '', field_value)
                if field_name not in data:
                    data[field_name] = field_value

            if data:
                entries.append(data)

        return entries

    def reprocess_failed_paper(self, paper_id, manual_data=None):
        """
        重新处理失败的论文。
        如果提供 manual_data，直接使用手动数据覆盖。
        """
        paper = Paper.query.get(paper_id)
        if not paper:
            return False, "论文不存在"

        if manual_data:
            paper.title = manual_data.get("title", paper.title)
            paper.authors = manual_data.get("authors", paper.authors)
            paper.year = manual_data.get("year", paper.year)
            paper.abstract = manual_data.get("abstract", paper.abstract)
            paper.category = manual_data.get("category", paper.category)
            paper.status = "success"
            db.session.commit()
            return True, "手动数据已保存"

        # 如果来源是 arXiv 且有 arxiv_id，重新拉取
        if paper.source_type == "arXiv" and paper.arxiv_id:
            return self.import_arxiv_by_id(paper.arxiv_id)

        return False, "无法自动重新处理，请提供手动数据"
