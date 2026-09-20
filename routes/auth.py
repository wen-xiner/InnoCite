"""
认证蓝图：登录、登出、会话管理。
"""

import logging
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, jsonify, current_app,
)
from models import db, User
from utils.response import api_error, ErrorCode

logger = logging.getLogger("InnoCite.Auth")

auth_bp = Blueprint("auth", __name__)


# ── 登录要求装饰器 ──
def login_required(f):
    """要求登录的视图装饰器。

    对 API/JSON 请求返回 401 JSON，对页面请求重定向到登录页。
    主要用于不需要全局拦截、仅个别路由需要灵活处理时使用。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/") or request.path.startswith("/import/"):
                return api_error(
                    "请先登录",
                    code=ErrorCode.UNAUTHORIZED, status=401,
                )
            flash("请先登录", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated


# ── 获取当前用户 ──
def get_current_user():
    """从 session 获取当前登录用户对象，未登录返回 None。"""
    user_id = session.get("user_id")
    if user_id:
        return User.query.get(user_id)
    return None


# ═══════════════════════════════════════════
# 登录 / 登出路由
# ═══════════════════════════════════════════

@auth_bp.route("/auth/login", methods=["GET", "POST"])
def login():
    """登录页面与登录处理"""
    # 已登录用户直接跳转首页
    if "user_id" in session:
        return redirect(url_for("papers.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("请输入用户名和密码", "warning")
            return render_template("login.html"), 400

        user = User.query.filter_by(username=username, is_active=True).first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["display_name"] = user.display_name or user.username
            session.permanent = True

            logger.info("用户 '%s' 登录成功", username)

            # 安全跳转：仅允许站内相对路径
            next_url = request.args.get("next", "")
            if next_url and not next_url.startswith("/"):
                next_url = ""
            if not next_url:
                next_url = url_for("papers.index")

            flash(f"欢迎回来，{session['display_name']}！", "success")
            return redirect(next_url)

        logger.warning("用户 '%s' 登录失败：密码错误或用户不存在", username)
        flash("用户名或密码错误", "danger")
        return render_template("login.html"), 401

    return render_template("login.html")


@auth_bp.route("/auth/register", methods=["GET", "POST"])
def register():
    """注册页面与注册处理"""
    # 已登录用户直接跳转首页
    if "user_id" in session:
        return redirect(url_for("papers.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        # 校验
        if not username or not password:
            flash("请填写用户名和密码", "warning")
            return render_template("login.html", register_mode=True), 400

        if len(username) < 2 or len(username) > 50:
            flash("用户名长度需在 2-50 个字符之间", "warning")
            return render_template("login.html", register_mode=True), 400

        if len(password) < 6:
            flash("密码长度不能少于 6 位", "warning")
            return render_template("login.html", register_mode=True), 400

        if password != password_confirm:
            flash("两次输入的密码不一致", "warning")
            return render_template("login.html", register_mode=True), 400

        # 检查用户名是否已存在
        existing = User.query.filter_by(username=username).first()
        if existing:
            flash("该用户名已被注册，请换一个", "warning")
            return render_template("login.html", register_mode=True), 400

        # 创建用户
        user = User(
            username=username,
            display_name=display_name or username,
            is_active=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        logger.info("新用户注册成功: '%s'", username)
        flash("注册成功！请使用新账号登录", "success")
        return redirect(url_for("auth.login"))

    return render_template("login.html", register_mode=True)


@auth_bp.route("/auth/logout")
def logout():
    """退出登录，清空会话"""
    username = session.get("username", "未知用户")
    session.clear()
    logger.info("用户 '%s' 已登出", username)
    flash("已退出登录", "info")
    return redirect(url_for("auth.login"))
