"""
后台任务队列模块。

使用 ThreadPoolExecutor 将耗时操作（创新点提取、推荐预计算、
嵌入向量计算）异步化，避免阻塞 HTTP 响应。

用法：
    from utils.task_queue import executor, run_in_background

    # Fire-and-forget 任务
    executor.submit(some_long_function, arg1, arg2)

    # 带完成回调的任务
    future = run_in_background(heavy_task, arg1)
    future.add_done_callback(lambda f: log_result(f.result()))
"""

import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("InnoCite.TaskQueue")

# 全局线程池：最多 3 个并发后台任务
executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="innocite-bg")

# Flask 应用实例引用（由 app.create_app 启动时通过 set_app 注入）。
# 后台线程没有请求/应用上下文，需要借助该引用创建独立的 app context，
# 从而获得线程独立的数据库 session，避免与请求线程共享 scoped session。
_app = None


def set_app(app):
    """注册 Flask 应用实例（由 create_app 调用，必须在启动任务前注入）。

    后台线程无请求上下文，必须通过 `app.app_context()` 创建独立上下文
    后才能安全访问数据库。该引用在应用创建时注入一次。
    """
    global _app
    _app = app


def run_in_background(func, *args, **kwargs):
    """提交任务到后台线程池执行，返回 Future 对象。

    与 executor.submit() 功能相同，但增加了异常日志。
    """
    def _wrapper():
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.warning(
                "后台任务异常: %s(*%s, **%s)",
                getattr(func, "__name__", func),
                args[:3] if len(args) > 3 else args,
                {k: v for k, v in list(kwargs.items())[:3]},
                exc_info=True,
            )
            return None

    return executor.submit(_wrapper)


def extract_innovation_async(paper):
    """异步提取单篇论文的创新点。

    后台线程使用「独立 app context + 独立数据库 session」：
    - 每次任务创建专属 app context，db.session 按 (线程, context) 隔离，
      不与请求线程共享 session；
    - 从独立 session 重新加载论文对象，避免跨线程使用请求线程的对象；
    - 任务结束由 app context 的清理机制自动关闭 session。

    解决旧实现共享模块级 db.session 导致的
    "database is locked" 及部分创新点静默丢失问题。
    """
    if _app is None:
        logger.error(
            "后台任务未注册应用实例（set_app 未调用），跳过创新点提取 (paper_id=%s)",
            getattr(paper, "id", None),
        )
        return

    from models import db, Paper, Innovation
    from innovation_extractor import InnovationExtractor

    paper_id = getattr(paper, "id", None)

    try:
        with _app.app_context():
            # 从独立 session 重新加载论文，避免跨线程使用请求线程的对象
            fresh_paper = db.session.get(Paper, paper_id)
            if fresh_paper is None:
                logger.warning("后台: 论文 %d 不存在，跳过", paper_id)
                return
            if fresh_paper.innovation is not None:
                logger.debug("后台: 论文 %d 已有创新点，跳过", paper_id)
                return
            if not fresh_paper.abstract:
                logger.debug("后台: 论文 %d 无摘要，跳过", paper_id)
                return

            result = InnovationExtractor().extract(fresh_paper)
            innovation = Innovation(
                paper_id=fresh_paper.id,
                problem=result["problem"],
                method=result["method"],
                effect=result["effect"],
                confidence=result["confidence"],
            )
            innovation.build_full_statement()
            db.session.add(innovation)
            db.session.commit()
            logger.debug("后台: 论文 %d 创新点提取成功", paper_id)
    except Exception:
        logger.warning("后台: 论文 %d 创新点提取失败", paper_id, exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass


def batch_extract_async(papers):
    """异步批量提取创新点。"""
    for paper in papers:
        executor.submit(extract_innovation_async, paper)
