"""
通用工具模块：提供分词、停用词加载、文本清洗、文件安全校验等公共函数。
"""

import os
import re
import struct
import jieba
import jieba.posseg as pseg

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 停用词缓存
_stopwords = None


def load_stopwords():
    """加载中英文停用词表，返回 set 对象。"""
    global _stopwords
    if _stopwords is not None:
        return _stopwords

    stopwords_path = os.path.join(BASE_DIR, "data", "stopwords.txt")
    _stopwords = set()
    try:
        with open(stopwords_path, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if word:
                    _stopwords.add(word)
    except FileNotFoundError:
        # 如果文件不存在，使用内置的最小停用词集
        _stopwords = {"的", "了", "在", "是", "the", "a", "an", "is", "are", "was"}

    # 添加一些额外的通用词
    _stopwords.update({
        "", " ", "\n", "\t", "\r",
        "～", "＠", "＃", "％", "＆", "＊",
        "（", "）", "【", "】", "《", "》",
        "＜", "＞", "：", "；", "，", "。",
        "！", "？", "…", "—", "～",
    })
    return _stopwords


def tokenize(text, remove_stopwords=True):
    """
    对文本进行分词，返回词汇列表。
    参数:
        text: 输入文本
        remove_stopwords: 是否移除停用词
    返回:
        分词后的词汇列表
    """
    if not text:
        return []

    # 清洗文本
    text = clean_text(text)

    # 分词
    words = jieba.lcut(text)

    if remove_stopwords:
        stopwords = load_stopwords()
        words = [w.strip() for w in words if w.strip() and w.strip() not in stopwords and len(w.strip()) > 1]

    return words


def tokenize_with_pos(text, remove_stopwords=True):
    """
    对文本进行词性标注分词，返回 (词汇, 词性) 列表。
    参数:
        text: 输入文本
        remove_stopwords: 是否移除停用词
    返回:
        [(word, pos), ...] 列表
    """
    if not text:
        return []

    text = clean_text(text)
    pairs = list(pseg.cut(text))

    result = []
    if remove_stopwords:
        stopwords = load_stopwords()
        for word, flag in pairs:
            w = word.strip()
            if w and w not in stopwords and len(w) > 1:
                result.append((w, flag))
    else:
        result = [(w.strip(), f) for w, f in pairs if w.strip()]

    return result


def extract_noun_phrases(text):
    """
    从文本中提取名词短语（连续的名词序列）。
    返回列表。
    """
    pos_pairs = tokenize_with_pos(text)
    if not pos_pairs:
        return []

    phrases = []
    current_phrase = []

    noun_tags = {"n", "nr", "ns", "nt", "nz", "ng", "vn", "an"}
    for word, flag in pos_pairs:
        if flag in noun_tags or flag.startswith("n"):
            current_phrase.append(word)
        else:
            if current_phrase:
                phrases.append("".join(current_phrase))
                current_phrase = []
            # 单独的名词或动词也保留
            if flag.startswith("v") or flag in {"eng"}:
                phrases.append(word)

    if current_phrase:
        phrases.append("".join(current_phrase))

    return phrases


def clean_text(text):
    """
    清洗文本：去除URL、特殊字符、多余空白等。
    """
    if not text:
        return ""

    # 去除URL
    text = re.sub(r'https?://\S+', '', text)
    # 去除email
    text = re.sub(r'\S+@\S+', '', text)
    # 去除LaTeX命令（常见于arXiv摘要）
    text = re.sub(r'\\[a-zA-Z]+\{.*?\}', '', text)
    # 去除多余的数学符号
    text = re.sub(r'\$.*?\$', '', text)
    # 保留字母、数字、中文、基本标点
    text = re.sub(r'[^一-鿿\w\s.,;:!?\-()[\]{}]', ' ', text)
    # 合并多余空白
    text = re.sub(r'\s+', ' ', text)
    # 去除独立数字行
    text = re.sub(r'(?<![a-zA-Z0-9_\-\.])\b\d+\b(?![a-zA-Z0-9_\-\.])', '', text)

    return text.strip()


def split_sentences(text):
    """
    将文本按中英文标点分句，返回句子列表。
    """
    if not text:
        return []

    # 分句标点
    text = re.sub(r'([。！？\.!?\n;；])', r'\1<SPLIT>', text)
    sentences = text.split('<SPLIT>')
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]


def find_conclusion_section(full_text):
    """
    从全文文本中定位结论/讨论段落。
    返回定位到的文本片段（最多2000字符）。
    """
    if not full_text:
        return ""

    # 结论相关的关键词模式
    conclusion_patterns = [
        r'(?i)(?:\d+\.?\s*)?(?:conclusion|concluding\s+remarks|discussion|summary)',
        r'(?:结论|总结|讨论|结语|小结)',
        r'(?i)(?:\d+\.?\s*)?(?:future\s+work|limitations)',
    ]

    for pattern in conclusion_patterns:
        match = re.search(pattern, full_text)
        if match:
            start = match.start()
            segment = full_text[start:start + 3000]
            return segment

    # 如果没找到明确标记，取文本末尾部分（通常是结论位置）
    if len(full_text) > 1000:
        return full_text[-2000:]

    return full_text


def has_numeric_indicator(text):
    """
    检查文本中是否包含数值指标（如百分比、分数等）。
    用于提升创新点置信度。
    """
    if not text:
        return False

    patterns = [
        r'\d+\.?\d*\s*%',
        r'\d+\.\d+',
        r'increase[sd]?\s+by\s+\d+',
        r'reduce[sd]?\s+by\s+\d+',
        r'(?:accuracy|precision|recall|f1|BLEU|mAP|AUC)\s*(?:of|:|=)\s*\d+',
        r'(?:提升|提高|降低|减少|达到)\s*\d+\.?\d*',
        r'outperform\w*\s+by\s+\d+',
        r'(?:state-of-the-art|SOTA)\s*(?:by|result)',
    ]

    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


# ═══════════════════════════════════════════════════
# 文件上传安全校验
# ═══════════════════════════════════════════════════

# 常见文件类型的魔数签名（前 N 个字节）
FILE_SIGNATURES = {
    "pdf": (
        b"%PDF-",
        "PDF 文档",
    ),
    "zip": (
        b"PK\x03\x04",
        "ZIP 压缩包",
    ),
    "rar": (
        b"Rar!\x1a\x07",
        "RAR 压缩包",
    ),
    "exe": (
        b"MZ",
        "Windows 可执行文件",
    ),
    "elf": (
        b"\x7fELF",
        "Linux 可执行文件",
    ),
    "png": (
        b"\x89PNG\r\n\x1a\n",
        "PNG 图片",
    ),
    "jpg": (
        b"\xff\xd8\xff",
        "JPEG 图片",
    ),
}

# 禁止上传的魔数类型（无论文件扩展名是什么）
BLOCKED_SIGNATURES = {"exe", "elf", "zip", "rar"}

# CSV 文件允许的最大字符集探测大小
CSV_DETECTION_SIZE = 4096


def get_file_signature(file_storage):
    """
    读取文件头部魔数签名。
    参数:
        file_storage: Flask FileStorage 对象
    返回:
        bytes: 文件头部 512 字节
    """
    file_storage.seek(0)
    signature = file_storage.read(512)
    file_storage.seek(0)  # 重置指针
    return signature


def validate_file_type(file_storage, expected_type="csv"):
    """
    校验上传文件的真实类型（基于魔数，而非扩展名）。
    参数:
        file_storage: Flask FileStorage 对象
        expected_type: "csv" 或 "pdf"
    返回:
        tuple: (is_valid: bool, error_message: str)
    """
    sig = get_file_signature(file_storage)

    # 首先检查是否为被禁止的类型（无论预期类型是什么）
    for blocked_type in BLOCKED_SIGNATURES:
        magic, label = FILE_SIGNATURES[blocked_type]
        if sig[:len(magic)] == magic:
            return False, f"不允许上传 {label}，请上传有效的 {expected_type.upper()} 文件"

    if expected_type == "pdf":
        pdf_magic = FILE_SIGNATURES["pdf"][0]
        if sig[:len(pdf_magic)] != pdf_magic:
            return False, "文件内容不是有效的 PDF 文档（缺少 PDF 签名），请上传正确的 PDF 文件"

    elif expected_type == "csv":
        chunk = sig[:CSV_DETECTION_SIZE]
        if b"\x00" in chunk:
            return False, "文件包含二进制数据，无法作为 CSV 导入"

        for sig_type, (magic, label) in FILE_SIGNATURES.items():
            if sig_type == "pdf":
                continue
            if chunk[:len(magic)] == magic:
                return False, f"文件内容看起来是 {label}，请上传纯文本 CSV 文件"

        if chunk[:5].lower() == b"%pdf-":
            return False, "文件内容看起来是 PDF 文档，请上传纯文本 CSV 文件"

        try:
            text = chunk.decode("utf-8", errors="strict")
            non_printable = sum(
                1 for c in text
                if c not in ("\n", "\r", "\t") and ord(c) < 32 and ord(c) != 0
            )
            if non_printable / max(len(text), 1) > 0.1:
                return False, "文件包含大量非打印字符，可能不是有效的 CSV 文本文件"
        except UnicodeDecodeError:
            return False, "文件编码不是有效的 UTF-8，无法作为 CSV 导入"

    return True, ""


def sanitize_upload_filename(filename):
    """
    清理上传文件名，移除路径遍历字符和危险字符。
    参数:
        filename: 原始文件名
    返回:
        str: 安全的文件名
    """
    if not filename:
        return "untitled"
    basename = os.path.basename(filename)
    safe = re.sub(r'[^\w一-鿿.\-]', '_', basename)
    safe = re.sub(r'_+', '_', safe)
    safe = safe.strip('_.')
    if not safe:
        safe = "untitled"
    return safe
