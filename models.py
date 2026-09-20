"""
数据模型定义（Pydantic）
从 main.py 拆分而来，新增了诊断（Diagnostic）相关的数据模型。
"""

from typing import Optional, List
from pydantic import BaseModel, Field


# ============================================================
# 原有模型（单次总结流程）
# ============================================================

class SummarizeRequest(BaseModel):
    """用户发起总结请求的数据结构"""
    raw_notes: str = Field(..., description="用户输入的零散记录文本")
    period: str = Field(default="本周", description="报告周期：本周/今日/本月")
    author_name: str = Field(default="", description="报告作者姓名（可选）")


class AgentResult(BaseModel):
    """单个Agent执行结果"""
    agent_name: str
    status: str
    output: str
    elapsed_hint: str


class SummarizeResponse(BaseModel):
    """完整的多Agent执行结果"""
    collector_result: AgentResult
    analyzer_result: AgentResult
    formatter_result: AgentResult
    final_report: str
    report_id: str


class ExportRequest(BaseModel):
    """导出Word文档请求"""
    report_id: str
    author_name: str = Field(default="")
    period: str = Field(default="本周")


class ReportSummary(BaseModel):
    """报告列表中的摘要信息（不含完整内容）"""
    report_id: str
    period: str
    created_at: str
    author_name: str
    preview: str    # 报告前100字的预览


class ReportListResponse(BaseModel):
    """历史报告列表响应"""
    reports: List[ReportSummary]
    total: int
    page: int
    page_size: int


class StatsResponse(BaseModel):
    """统计数据响应"""
    total_reports: int
    period_distribution: dict
    latest_report_date: str
    this_month_count: int


# ============================================================
# 新增模型（跨周期诊断功能）
# ============================================================

class DiagnoseRequest(BaseModel):
    """
    触发诊断请求的数据结构

    两种用法二选一：
    1. 传 report_ids：精确指定要分析哪几条报告（用户在历史报告列表里手动勾选）
    2. 不传 report_ids，传 report_count：自动取最近N条报告（兼容原有用法）
    """
    report_ids: Optional[List[str]] = Field(
        default=None,
        description="用户手动勾选的报告ID列表，传了此字段则优先按此列表分析，忽略report_count"
    )
    report_count: int = Field(
        default=4,
        ge=2,
        le=20,
        description="未传report_ids时生效：分析最近N条历史报告，默认4条"
    )
    author_name: Optional[str] = Field(
        default=None,
        description="可选，按作者姓名过滤历史报告（仅在未传report_ids时生效）"
    )


class ProblemPattern(BaseModel):
    """
    单个重复出现的问题模式
    对应 DiagnosticAgent 第一阶段（模式识别）的结构化输出
    """
    issue: str = Field(..., description="问题/瓶颈的简要描述")
    occurrence_count: int = Field(..., description="在分析范围内出现的次数")
    related_report_ids: List[str] = Field(
        default_factory=list,
        description="支撑该判断的历史报告ID列表，用于溯源"
    )
    related_dates: List[str] = Field(
        default_factory=list,
        description="对应的报告生成日期，便于前端展示"
    )


class DiagnosticSuggestion(BaseModel):
    """
    单条改进建议
    对应 DiagnosticAgent 第二阶段（诊断建议）的结构化输出
    每条建议都必须能追溯到具体的问题模式，避免空泛通用的建议
    """
    related_issue: str = Field(..., description="该建议针对的问题描述，对应ProblemPattern.issue")
    suggestion: str = Field(..., description="具体可执行的改进建议")
    evidence: str = Field(..., description="给出建议的依据说明，引用具体日期/记录")


class DiagnoseResponse(BaseModel):
    """跨周期诊断的完整响应"""
    diagnosis_id: str
    analyzed_report_count: int
    analyzed_report_ids: List[str]
    patterns: List[ProblemPattern]
    suggestions: List[DiagnosticSuggestion]
    overall_summary: str = Field(..., description="一句话总体诊断结论")
    created_at: str
