"""
GROBID 学术 PDF 解析客户端。

通过 GROBID 的 REST API 从 PDF 中提取学术元数据（标题、作者、年份、摘要）。
GROBID 服务需通过 Docker 启动：

    docker run -d -p 8070:8070 lfoppiano/grobid:0.8.1

仅实现项目需要的两个端点：
  - GET  {url}/isalive                  健康检查
  - POST {url}/api/processHeaderDocument  提取论文头部元数据（TEI XML）

与 pdfplumber 形成双轨：GROBID 优先（机器学习），不可用时由调用方回退。
"""

import logging
import re
import threading
import time
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger("InnoCite.GrobidClient")

# GROBID TEI XML 命名空间
_TEI_NS = {
    "tei": "http://www.tei-c.org/ns/1.0",
}

# ── 可用性探测缓存 ──
# 未部署 GROBID 时，每次 PDF 导入都做一次 3 秒超时的网络探测会白等。
# 缓存探测结果：可用状态缓存 5 分钟，不可用状态缓存 30 秒
# （短一点，便于用户中途启动 GROBID 后尽快生效）。
_AVAILABILITY_CACHE = {"value": None, "timestamp": 0.0}
_AVAILABILITY_TTL_AVAILABLE = 300.0   # 秒
_AVAILABILITY_TTL_UNAVAILABLE = 30.0  # 秒
_AVAILABILITY_LOCK = threading.Lock()


def is_available(grobid_url="http://localhost:8070", timeout=3):
    """检查 GROBID 服务是否在线（带 TTL 缓存，避免每次导入白等超时）。

    GROBID 提供 /isalive 端点，返回 HTTP 200 表示服务可用。
    首次调用会真实探测；缓存有效期内直接返回上次结果。
    """
    now = time.monotonic()
    with _AVAILABILITY_LOCK:
        cached = _AVAILABILITY_CACHE["value"]
        cached_at = _AVAILABILITY_CACHE["timestamp"]
        if cached is not None:
            ttl = (
                _AVAILABILITY_TTL_AVAILABLE if cached
                else _AVAILABILITY_TTL_UNAVAILABLE
            )
            if (now - cached_at) < ttl:
                return cached

    result = _probe_available(grobid_url, timeout)

    with _AVAILABILITY_LOCK:
        _AVAILABILITY_CACHE["value"] = result
        _AVAILABILITY_CACHE["timestamp"] = now
    return result


def _probe_available(grobid_url, timeout):
    """实际执行 GROBID 可用性探测（无缓存）。"""
    try:
        resp = requests.get(
            f"{grobid_url.rstrip('/')}/isalive",
            timeout=timeout,
        )
        return resp.status_code == 200
    except requests.RequestException:
        logger.debug("GROBID 服务不可达: %s", grobid_url)
        return False


def extract_header(
    pdf_path,
    grobid_url="http://localhost:8070",
    timeout=30,
):
    """从 PDF 提取论文头部元数据。

    参数:
        pdf_path: PDF 文件路径
        grobid_url: GROBID 服务地址
        timeout: 请求超时秒数

    返回:
        dict: {"title", "authors", "year", "abstract"}，
              解析失败或字段缺失时对应值为 None。
    """
    import os

    if not os.path.isfile(pdf_path):
        logger.warning("PDF 文件不存在: %s", pdf_path)
        return None

    endpoint = f"{grobid_url.rstrip('/')}/api/processHeaderDocument"
    try:
        with open(pdf_path, "rb") as f:
            resp = requests.post(
                endpoint,
                files={"input": (os.path.basename(pdf_path), f, "application/pdf")},
                timeout=timeout,
            )
    except requests.RequestException as e:
        logger.warning("GROBID 请求失败: %s", e)
        return None

    if resp.status_code != 200:
        logger.warning(
            "GROBID 返回异常状态码 %s: %s",
            resp.status_code,
            resp.text[:200],
        )
        return None

    return _parse_tei(resp.text)


def _parse_tei(tei_xml):
    """解析 GROBID 返回的 TEI XML，提取头部元数据。"""
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as e:
        logger.warning("GROBID TEI XML 解析失败: %s", e)
        return None

    def _find(path):
        elem = root.find(path, _TEI_NS)
        return elem.text.strip() if elem is not None and elem.text else None

    # ── 标题 ──
    title = _find("./tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title")

    # ── 作者（可能多个 <author> 节点）──
    authors = []
    author_nodes = root.findall(
        "./tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author",
        _TEI_NS,
    )
    for author in author_nodes:
        # 优先取 persName 下的完整姓名，退化为文本内容
        name = _find_from(author, "tei:persName")
        if not name:
            name = _text_content(author)
        if name:
            authors.append(name)

    # ── 年份（优先 date[@type='published']，退化到任意 date）──
    year = None
    date_node = root.find(
        "./tei:teiHeader/tei:fileDesc/tei:publicationStmt/tei:date[@type='published']",
        _TEI_NS,
    )
    if date_node is None:
        date_node = root.find(
            "./tei:teiHeader/tei:fileDesc/tei:publicationStmt/tei:date",
            _TEI_NS,
        )
    if date_node is not None:
        year = date_node.get("when") or date_node.text
        if year:
            m = re.search(r"(19|20)\d{2}", year)
            year = m.group(0) if m else None

    # ── 摘要（profileDesc 下的 abstract）──
    abstract = None
    abstract_elems = root.findall(
        "./tei:teiHeader/tei:profileDesc/tei:abstract/tei:p",
        _TEI_NS,
    )
    if abstract_elems:
        abstract = "\n".join(
            _text_content(p) for p in abstract_elems if _text_content(p)
        )

    meta = {
        "title": title,
        "authors": "; ".join(authors) if authors else None,
        "year": int(year) if year and year.isdigit() else None,
        "abstract": abstract,
    }
    logger.info(
        "GROBID 解析完成: 标题=%s, 作者=%d 位, 年份=%s",
        (title or "")[:50],
        len(authors),
        year,
    )
    return meta


def _find_from(node, path):
    """在给定节点下查找子节点文本。"""
    elem = node.find(path, _TEI_NS)
    return elem.text.strip() if elem is not None and elem.text else None


def _text_content(node):
    """获取节点及其子节点的全部文本内容（含尾随空格清理）。"""
    if node is None:
        return ""
    parts = [t for t in node.itertext() if t and t.strip()]
    return " ".join(p.strip() for p in parts).strip()
