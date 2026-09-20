"""
轻量级 Gzip 响应压缩中间件（零外部依赖）。

对 JSON / HTML / CSS / JS / CSV 等文本响应自动进行 gzip 压缩，
减少传输体积 60-80%，显著提升页面加载速度。

用法：
    from utils.gzip_middleware import GzipMiddleware
    app.wsgi_app = GzipMiddleware(app.wsgi_app)
"""

import gzip
import io


# 需要压缩的 MIME 类型
_COMPRESSIBLE_TYPES = frozenset({
    "application/json",
    "text/html",
    "text/css",
    "text/javascript",
    "application/javascript",
    "text/csv",
    "text/plain",
    "application/xml",
    "text/xml",
})

# 小于此大小的响应不压缩（压缩小内容反而增加开销）
_MIN_LENGTH = 500


class GzipMiddleware:
    """对符合条件的 WSGI 响应进行 gzip 压缩。"""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        accept_encoding = environ.get("HTTP_ACCEPT_ENCODING", "")
        if "gzip" not in accept_encoding.lower():
            return self.app(environ, start_response)

        # 捕获原始响应
        status = []
        headers = []
        body_chunks = []

        def _capture(status_str, header_list, exc_info=None):
            status.append(status_str)
            headers.extend(header_list)

        try:
            response = self.app(environ, _capture)
        except Exception:
            # 应用层异常时透传
            return self.app(environ, start_response)

        # 收集响应体
        for chunk in response:
            body_chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
        body = b"".join(body_chunks)

        # 判断是否应压缩
        content_type = ""
        for name, value in headers:
            if name.lower() == "content-type":
                content_type = value.split(";")[0].strip()
                break

        if content_type not in _COMPRESSIBLE_TYPES or len(body) < _MIN_LENGTH:
            start_response(status[0], headers)
            return [body]

        # 压缩
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=4) as gz:
            gz.write(body)
        compressed = buf.getvalue()

        # 更新响应头
        new_headers = []
        has_content_length = False
        for name, value in headers:
            low = name.lower()
            if low == "content-length":
                new_headers.append((name, str(len(compressed))))
                has_content_length = True
            elif low == "content-encoding":
                pass  # 移除旧的编码头
            else:
                new_headers.append((name, value))
        if not has_content_length:
            new_headers.append(("Content-Length", str(len(compressed))))
        new_headers.append(("Content-Encoding", "gzip"))
        new_headers.append(("Vary", "Accept-Encoding"))

        start_response(status[0], new_headers)
        return [compressed]
