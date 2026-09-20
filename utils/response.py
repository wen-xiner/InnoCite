"""
统一 API 响应格式模块。

所有 API 端点使用以下方法构建 JSON 响应，确保格式一致：
  - api_success(data, message)  → 200
  - api_error(message, code, status)  → 4xx/5xx
  - api_paginated(items, page, per_page, total)  → 200（分页）

错误码常量定义在 ErrorCode 类中，方便前后端统一约定。
"""

from flask import jsonify


class ErrorCode:
    """API 错误码常量（前后端约定）。"""
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    CSRF_ERROR = "csrf_error"
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    INTERNAL_ERROR = "internal_error"
    FILE_TYPE_ERROR = "file_type_error"
    DUPLICATE_ENTRY = "duplicate_entry"


def api_success(data=None, message=None, **extra_fields):
    """构建成功响应。

    dict 类型的 data 会被扁平合并到响应顶层（向后兼容旧前端），
    非 dict 类型（list/str 等）则包装在 "data" 字段中。

    返回示例:
        api_success(data={"kw": [...]}) → {"success": true, "kw": [...]}
        api_success(data=[1,2,3])       → {"success": true, "data": [1,2,3]}
    """
    body = {"success": True}
    if data is not None:
        if isinstance(data, dict):
            body.update(data)
        else:
            body["data"] = data
    if message is not None:
        body["message"] = message
    body.update(extra_fields)
    return jsonify(body)


def api_error(message, code=None, status=400):
    """构建错误响应。

    返回:
        JSON: {"success": false, "message": ..., "code": ...}
    """
    body = {"success": False, "message": message}
    if code:
        body["code"] = code
    return jsonify(body), status


def api_paginated(items, page, per_page, total, **extra_fields):
    """构建分页响应。

    返回:
        JSON: {"success": true, "data": [...], "page": ..., "per_page": ...,
               "total": ..., "total_pages": ...}
    """
    body = {
        "success": True,
        "data": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }
    body.update(extra_fields)
    return jsonify(body)
