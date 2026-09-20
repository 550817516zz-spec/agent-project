"""
持久化存储模块
从 main.py 拆分而来。将报告数据存储到本地 JSON 文件，程序重启后历史记录不丢失。
新增了诊断报告（diagnoses.json）的存储，与进度报告（reports.json）分开存放，
避免诊断记录混入普通报告列表，影响 /api/reports 的分页与统计逻辑。
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("storage")

DATA_DIR = Path("data")
REPORTS_FILE = DATA_DIR / "reports.json"
DIAGNOSES_FILE = DATA_DIR / "diagnoses.json"


def init_storage():
    """
    初始化本地存储目录和文件。
    如果 data 目录、reports.json 或 diagnoses.json 不存在，自动创建。
    程序启动时调用一次。
    """
    DATA_DIR.mkdir(exist_ok=True)

    if not REPORTS_FILE.exists():
        REPORTS_FILE.write_text(
            json.dumps({"reports": []}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        logger.info("初始化存储文件：data/reports.json")

    if not DIAGNOSES_FILE.exists():
        DIAGNOSES_FILE.write_text(
            json.dumps({"diagnoses": []}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        logger.info("初始化存储文件：data/diagnoses.json")


# ============================================================
# 进度报告存储（原有逻辑，未改动）
# ============================================================

def load_reports() -> list:
    """
    从 JSON 文件加载所有历史报告。

    返回：
        报告列表，每条为 dict，包含 report_id、period、created_at、final_report 等字段
    """
    try:
        content = REPORTS_FILE.read_text(encoding="utf-8")
        data = json.loads(content)
        return data.get("reports", [])
    except Exception as e:
        logger.error(f"加载报告文件失败: {e}")
        return []


def save_report(report_data: dict):
    """
    将一条新报告追加保存到 JSON 文件。

    参数：
        report_data: 报告数据字典，包含完整的报告内容和元信息
    """
    try:
        reports = load_reports()
        reports.append(report_data)
        content = json.dumps({"reports": reports}, ensure_ascii=False, indent=2)
        REPORTS_FILE.write_text(content, encoding="utf-8")
        logger.info(f"报告已持久化存储：{report_data.get('report_id')}")
    except Exception as e:
        logger.error(f"保存报告失败: {e}")


def delete_report_by_id(report_id: str) -> bool:
    """
    根据 report_id 从 JSON 文件中删除指定报告。

    参数：
        report_id: 要删除的报告ID

    返回：
        True 表示删除成功，False 表示未找到该报告
    """
    try:
        reports = load_reports()
        original_count = len(reports)
        reports = [r for r in reports if r.get("report_id") != report_id]

        if len(reports) == original_count:
            return False  # 没找到，什么都没删

        content = json.dumps({"reports": reports}, ensure_ascii=False, indent=2)
        REPORTS_FILE.write_text(content, encoding="utf-8")
        logger.info(f"报告已删除：{report_id}")
        return True
    except Exception as e:
        logger.error(f"删除报告失败: {e}")
        return False


def get_report_by_id(report_id: str) -> Optional[dict]:
    """
    根据 report_id 查找单条报告。

    参数：
        report_id: 要查找的报告ID

    返回：
        找到则返回报告 dict，未找到返回 None
    """
    reports = load_reports()
    for r in reports:
        if r.get("report_id") == report_id:
            return r
    return None


def get_reports_by_ids(report_ids: list) -> list:
    """
    根据用户手动勾选的 report_id 列表，取出对应的完整报告。
    返回顺序按 report_ids 传入的顺序排列，找不到的ID会被跳过（不报错）。

    参数：
        report_ids: 要获取的报告ID列表

    返回：
        对应的报告 dict 列表
    """
    all_reports = load_reports()
    reports_by_id = {r.get("report_id"): r for r in all_reports}
    result = []
    for rid in report_ids:
        if rid in reports_by_id:
            result.append(reports_by_id[rid])
    return result


def get_recent_reports(count: int, author_name: Optional[str] = None) -> list:
    """
    获取最近N条历史报告，供 DiagnosticAgent 做跨周期分析使用。

    参数：
        count: 要获取的报告数量
        author_name: 可选，按作者姓名过滤

    返回：
        按创建时间倒序排列的最近N条报告（最新的在最前面）
    """
    reports = load_reports()
    if author_name:
        reports = [r for r in reports if r.get("author_name") == author_name]
    reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return reports[:count]


# ============================================================
# 诊断报告存储（新增）
# ============================================================

def load_diagnoses() -> list:
    """从 JSON 文件加载所有历史诊断记录"""
    try:
        content = DIAGNOSES_FILE.read_text(encoding="utf-8")
        data = json.loads(content)
        return data.get("diagnoses", [])
    except Exception as e:
        logger.error(f"加载诊断文件失败: {e}")
        return []


def save_diagnosis(diagnosis_data: dict):
    """
    将一条新的诊断结果追加保存到 JSON 文件。

    参数：
        diagnosis_data: 诊断数据字典，对应 DiagnoseResponse 的内容
    """
    try:
        diagnoses = load_diagnoses()
        diagnoses.append(diagnosis_data)
        content = json.dumps({"diagnoses": diagnoses}, ensure_ascii=False, indent=2)
        DIAGNOSES_FILE.write_text(content, encoding="utf-8")
        logger.info(f"诊断结果已持久化存储：{diagnosis_data.get('diagnosis_id')}")
    except Exception as e:
        logger.error(f"保存诊断结果失败: {e}")
