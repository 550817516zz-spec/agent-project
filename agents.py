"""
Agent 核心类定义
从 main.py 拆分而来。

包含：
- BaseAgent：所有Agent的基类，封装调用DeepSeek API的通用逻辑
- CollectorAgent：采集Agent，整理和分类用户的零散输入记录
- AnalyzerAgent：分析Agent，对采集结果进行深度分析（单周期）
- FormatterAgent：格式化Agent，生成结构化报告
- DiagnosticAgent：诊断Agent（新增），跨周期识别重复问题模式并给出有依据的改进建议
"""

import json
import logging
from typing import List

from openai import OpenAI

from models import AgentResult, ProblemPattern, DiagnosticSuggestion

logger_root = logging.getLogger("agents")


class BaseAgent:
    """
    所有Agent的基类。
    封装了调用DeepSeek API的通用逻辑，子类只需定义system_prompt和处理逻辑。
    """

    def __init__(self, name: str, system_prompt: str, client: OpenAI):
        """
        初始化Agent

        参数:
            name: Agent的名称，用于日志和前端展示
            system_prompt: 该Agent的系统提示词，决定了它的角色和行为
            client: 已配置好的 OpenAI 兼容客户端（指向 DeepSeek API）
        """
        self.name = name
        self.system_prompt = system_prompt
        self.client = client
        self.logger = logging.getLogger(f"agent.{name}")

    def call_llm(self, user_message: str, temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """
        调用大语言模型接口

        参数:
            user_message: 发给模型的用户消息内容
            temperature: 生成温度，越高越有创意，越低越稳定
            max_tokens: 最大生成token数

        返回:
            模型返回的文本内容
        """
        self.logger.info(f"[{self.name}] 开始调用 DeepSeek API")

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            result = response.choices[0].message.content
            self.logger.info(f"[{self.name}] API调用成功，返回 {len(result)} 字符")
            return result

        except Exception as e:
            self.logger.error(f"[{self.name}] API调用失败: {str(e)}")
            raise

    def run(self, *args, **kwargs) -> AgentResult:
        """子类必须实现此方法"""
        raise NotImplementedError("子类必须实现 run() 方法")


class CollectorAgent(BaseAgent):
    """
    采集Agent：负责整理和分类用户的零散输入记录

    职责：
    1. 识别记录中涉及的日期、项目、任务类型
    2. 对零散内容进行去重和归类
    3. 以结构化的JSON格式输出，供下游Agent使用
    """

    SYSTEM_PROMPT = """你是一个数据采集整理专家，负责处理用户的零散学习/工作记录。

你的任务是：
1. 仔细阅读用户输入的所有零散记录
2. 识别其中的日期信息（如"周一"、"3号"等）
3. 将记录按类型分类：代码开发、学习笔记、课程作业、遇到的问题、其他
4. 去除重复或冗余的内容
5. 以结构化JSON格式输出整理结果

输出格式必须是合法JSON，结构如下：
{
  "total_records": 记录条数,
  "date_range": "涉及的时间范围描述",
  "categories": {
    "开发任务": ["任务1", "任务2"],
    "学习内容": ["内容1"],
    "课程作业": ["作业1"],
    "遇到的问题": ["问题1"],
    "其他": ["其他1"]
  },
  "summary": "一句话概括这段时间的整体状态"
}

注意：只输出JSON，不要有任何多余的解释文字。"""

    def __init__(self, client: OpenAI):
        super().__init__(name="CollectorAgent", system_prompt=self.SYSTEM_PROMPT, client=client)

    def run(self, input_text: str) -> AgentResult:
        """
        执行采集和分类任务

        参数:
            input_text: 用户输入的原始零散记录

        返回:
            AgentResult，output字段为整理好的JSON字符串
        """
        self.logger.info("开始采集和分类原始记录")

        try:
            raw_output = self.call_llm(input_text, temperature=0.3)

            cleaned = raw_output.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])

            json.loads(cleaned)  # 验证JSON合法性

            return AgentResult(
                agent_name=self.name,
                status="success",
                output=cleaned,
                elapsed_hint="采集完成"
            )

        except json.JSONDecodeError:
            fallback = json.dumps({
                "total_records": 1,
                "date_range": "本周期",
                "categories": {
                    "开发任务": [],
                    "学习内容": [],
                    "课程作业": [],
                    "遇到的问题": [],
                    "其他": [input_text]
                },
                "summary": "记录已接收，等待分析"
            }, ensure_ascii=False)
            return AgentResult(
                agent_name=self.name,
                status="success",
                output=fallback,
                elapsed_hint="采集完成（降级模式）"
            )

        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                status="error",
                output=str(e),
                elapsed_hint="采集失败"
            )


class AnalyzerAgent(BaseAgent):
    """
    分析Agent：对采集结果进行深度分析（单周期）

    职责：
    1. 分析完成情况和效率
    2. 识别卡点和潜在风险
    3. 基于历史规律提出改进建议
    4. 生成结构化分析结论
    """

    SYSTEM_PROMPT = """你是一个擅长学习效率分析的专家顾问，负责分析大学生的学习/项目进度。

你会收到一份由采集Agent整理好的JSON格式记录摘要。

你的分析任务：
1. 评估这段时间的完成情况（完成了多少、质量如何）
2. 识别遇到的卡点和困难，分析可能的原因
3. 发现值得表扬的地方（哪怕是很小的进步）
4. 给出3条具体可行的改进建议
5. 预判下一步可能遇到的风险

输出格式要求：
- 用中文输出
- 分析要有深度，不要泛泛而谈
- 总长度控制在400字以内
- 按以下结构输出（使用这些标题）：

【完成情况评估】
...

【主要卡点分析】
...

【改进建议】
1. ...
2. ...
3. ...

【下周风险预判】
..."""

    def __init__(self, client: OpenAI):
        super().__init__(name="AnalyzerAgent", system_prompt=self.SYSTEM_PROMPT, client=client)

    def run(self, collected_json: str) -> AgentResult:
        """
        执行深度分析

        参数:
            collected_json: CollectorAgent输出的JSON字符串
        """
        self.logger.info("开始深度分析采集结果")

        try:
            analysis = self.call_llm(
                f"请分析以下学习/项目记录摘要：\n\n{collected_json}",
                temperature=0.6
            )
            return AgentResult(
                agent_name=self.name,
                status="success",
                output=analysis,
                elapsed_hint="分析完成"
            )
        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                status="error",
                output=str(e),
                elapsed_hint="分析失败"
            )


class FormatterAgent(BaseAgent):
    """
    格式化Agent：将分析结果整合成完整的进度报告

    职责：
    1. 整合采集数据和分析结论
    2. 生成格式规范、易读的报告
    3. 报告结构包括：封面信息、本期完成事项、问题分析、下期计划
    4. 文字风格专业但不生硬
    """

    SYSTEM_PROMPT = """你是一个专业的报告撰写助手，负责将分析结果整合成格式规范的进度报告。

你会收到：
1. 采集Agent整理的结构化记录（JSON格式）
2. 分析Agent提供的深度分析结论

你需要生成一份完整的进度报告，格式如下（严格按照此结构）：

# 进度报告

## 一、本期完成事项

（根据采集数据，列出具体完成的任务，分点描述，每点1-2句话）

## 二、遇到的问题与卡点

（整合遇到的问题，说明影响和现状）

## 三、分析与反思

（基于分析Agent的结论，用自己的语言重新表述，要有个人视角）

## 四、下期计划

（根据当前进展，列出3-5条具体可执行的下期计划）

---
报告由进度总结Agent自动生成

要求：
- 中文输出
- 语气专业、真实，不要太客套
- 总字数在500-800字之间
- 不要输出JSON，直接输出报告正文"""

    def __init__(self, client: OpenAI):
        super().__init__(name="FormatterAgent", system_prompt=self.SYSTEM_PROMPT, client=client)

    def run(self, collected_json: str, analysis_text: str, period: str) -> AgentResult:
        """
        执行报告格式化

        参数:
            collected_json: CollectorAgent的输出
            analysis_text: AnalyzerAgent的输出
            period: 报告周期（本周/今日/本月）
        """
        self.logger.info("开始生成最终报告")

        combined_input = f"""报告周期：{period}

【采集Agent整理的记录】
{collected_json}

【分析Agent的分析结论】
{analysis_text}"""

        try:
            report = self.call_llm(combined_input, temperature=0.7)
            return AgentResult(
                agent_name=self.name,
                status="success",
                output=report,
                elapsed_hint="报告生成完成"
            )
        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                status="error",
                output=str(e),
                elapsed_hint="报告生成失败"
            )


class DiagnosticAgent(BaseAgent):
    """
    诊断Agent（新增）：跨周期识别重复出现的问题模式，给出有据可查的改进建议

    与 AnalyzerAgent 的区别：
    - AnalyzerAgent 只看"这一次"的记录，做单周期分析
    - DiagnosticAgent 看"最近N次"历史报告，找规律、给根因分析

    采用两阶段设计，体现"分析决策"的过程感：
    阶段1（模式识别）：从多条历史报告中提取反复出现的问题，输出结构化JSON，
                        并标注每个问题具体出现在哪几次报告里（用于溯源）
    阶段2（诊断建议）：基于阶段1识别出的问题模式，生成具体、有依据的改进建议，
                        每条建议必须说明"基于哪几次记录"，避免空泛的通用建议
    """

    PATTERN_SYSTEM_PROMPT = """你是一个进度分析专家，擅长从用户多期的进度报告中发现反复出现的问题、瓶颈或情绪倾向。

你会收到用户最近若干期的进度报告全文，每条报告都标注了 report_id 和 created_at（生成日期）。

你的任务：
1. 仔细比对多期报告内容，找出其中反复出现（至少出现2次以上）的问题、瓶颈或困难
2. 不要罗列每一期都有的琐碎小事，只关注真正重复、有规律性的问题
3. 对每个识别出的问题，记录它具体出现在哪些报告里（report_id 和对应日期）

输出格式必须是合法JSON，结构如下：
{
  "patterns": [
    {
      "issue": "问题的简要描述，例如：进度报告中反复提到测试环节耗时过长",
      "occurrence_count": 3,
      "related_report_ids": ["20260701_093000", "20260708_091500"],
      "related_dates": ["2026-07-01", "2026-07-08"]
    }
  ],
  "overall_summary": "一句话总体诊断结论"
}

注意：
- 如果多期报告中没有发现任何重复模式，patterns 返回空数组即可，不要为了凑数而牵强附会
- 只输出JSON，不要有任何多余的解释文字"""

    SUGGESTION_SYSTEM_PROMPT = """你是一个资深的效率改进顾问。

你会收到一份"重复问题模式"清单（每条都包含问题描述、出现次数、涉及的具体日期）。

你的任务：
针对清单中的每一个问题模式，给出一条具体、可立即执行的改进建议。

严格要求：
1. 建议必须具体可执行，禁止"要加强时间管理""要提高效率"这类空泛的话
2. 每条建议必须在 evidence 字段里说明依据，明确引用是基于哪些日期的记录得出的判断
3. 建议数量必须与问题模式数量一一对应

输出格式必须是合法JSON，结构如下：
{
  "suggestions": [
    {
      "related_issue": "对应的问题描述（需与输入的issue完全一致）",
      "suggestion": "具体可执行的改进建议",
      "evidence": "依据说明，例如：该问题在2026-07-01、2026-07-08、2026-07-15的记录中均有提及"
    }
  ]
}

注意：只输出JSON，不要有任何多余的解释文字。"""

    def __init__(self, client: OpenAI):
        # 父类需要一个默认 system_prompt，这里传入阶段1的prompt作为默认值，
        # 实际调用时通过 self.client 直接构造两阶段各自的请求
        super().__init__(name="DiagnosticAgent", system_prompt=self.PATTERN_SYSTEM_PROMPT, client=client)

    def _call_stage(self, system_prompt: str, user_message: str, temperature: float = 0.4) -> str:
        """内部方法：按指定的 system_prompt 调用一次LLM，用于区分两个阶段"""
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=temperature,
            max_tokens=2000
        )
        return response.choices[0].message.content

    @staticmethod
    def _parse_json_block(raw_output: str) -> dict:
        """去除可能的 markdown 代码块包裹，解析JSON"""
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])
        return json.loads(cleaned)

    def run(self, recent_reports: List[dict]) -> AgentResult:
        """
        执行跨周期诊断

        参数:
            recent_reports: 最近N条历史报告的列表（每条为dict，需包含
                             report_id、created_at、final_report 等字段）

        返回:
            AgentResult，output字段为JSON字符串，包含 patterns / suggestions / overall_summary
        """
        self.logger.info(f"开始跨周期诊断，共 {len(recent_reports)} 条历史报告")

        if len(recent_reports) < 2:
            return AgentResult(
                agent_name=self.name,
                status="error",
                output="历史报告数量不足2条，无法进行跨周期对比诊断",
                elapsed_hint="诊断中止"
            )

        try:
            # ---------- 阶段1：模式识别 ----------
            reports_text = "\n\n".join([
                f"[report_id: {r.get('report_id')}, 日期: {r.get('created_at', '')[:10]}]\n"
                f"{r.get('final_report', '')}"
                for r in recent_reports
            ])

            self.logger.info("阶段1：模式识别 运行中")
            pattern_raw = self._call_stage(
                self.PATTERN_SYSTEM_PROMPT,
                f"以下是用户最近{len(recent_reports)}期的进度报告：\n\n{reports_text}",
                temperature=0.4
            )
            pattern_data = self._parse_json_block(pattern_raw)
            patterns = pattern_data.get("patterns", [])
            overall_summary = pattern_data.get("overall_summary", "")

            # 没有识别出重复模式，直接返回，不再进行阶段2
            if not patterns:
                result_data = {
                    "patterns": [],
                    "suggestions": [],
                    "overall_summary": overall_summary or "未发现明显的重复问题模式，近期状态较为稳定。"
                }
                return AgentResult(
                    agent_name=self.name,
                    status="success",
                    output=json.dumps(result_data, ensure_ascii=False),
                    elapsed_hint="诊断完成（未发现重复问题）"
                )

            # ---------- 阶段2：诊断建议 ----------
            self.logger.info("阶段2：诊断建议 运行中")
            patterns_text = json.dumps({"patterns": patterns}, ensure_ascii=False, indent=2)
            suggestion_raw = self._call_stage(
                self.SUGGESTION_SYSTEM_PROMPT,
                f"以下是识别出的重复问题模式：\n\n{patterns_text}",
                temperature=0.5
            )
            suggestion_data = self._parse_json_block(suggestion_raw)
            suggestions = suggestion_data.get("suggestions", [])

            result_data = {
                "patterns": patterns,
                "suggestions": suggestions,
                "overall_summary": overall_summary
            }

            return AgentResult(
                agent_name=self.name,
                status="success",
                output=json.dumps(result_data, ensure_ascii=False),
                elapsed_hint="诊断完成"
            )

        except json.JSONDecodeError as e:
            return AgentResult(
                agent_name=self.name,
                status="error",
                output=f"模型输出解析失败: {str(e)}",
                elapsed_hint="诊断失败"
            )
        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                status="error",
                output=str(e),
                elapsed_hint="诊断失败"
            )
