"""Research Planner — generates structured research plans using LLM."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from core.adapters.llm import create_llm
from core.interfaces import LLM, LLMMessage
from core.logging import logger

RESEARCH_PLAN_SYSTEM_PROMPT = (
    "You are a professional investment research analyst. "
    "Given a research question, create a structured research plan.\n\n"
    "Your plan must include:\n"
    "1. **research_goal**: A clear restatement of what needs to be researched\n"
    "2. **sub_questions**: 3-6 specific questions that must be answered "
    "to reach a conclusion. Each sub-question should have a unique ID, "
    "priority level (high/medium/low), and status (pending/in_progress/completed)\n"
    "3. **analysis_dimensions**: Key dimensions to analyze (e.g., financial "
    "health, competitive position, industry trends, management quality, "
    "valuation, risks)\n"
    "4. **data_requirements**: What specific data points are needed\n"
    "5. **suggested_sources**: Types of documents or data sources to consult"
    "\nRespond with valid JSON only, no markdown formatting."
)

PLAN_KEY = "research_plan"


def _item(text: str, priority: str = "medium") -> dict:
    """构造 ResearchPlanItem 字典（id 随机，status=pending）。"""
    return {
        "id": str(uuid4())[:8],
        "text": text,
        "priority": priority,
        "status": "pending",
    }


# 预置研究类型模板：plan_type 命中即直接使用（零 LLM 调用、产出稳定）。
# 后续可迁移到 ai.prompt_templates 表做用户自定义（name=research_plan_<type>）。
PLAN_TEMPLATES: dict[str, dict] = {
    "initial": {
        "research_goal": "完成公司首次覆盖：基本面、行业位置与估值定价",
        "sub_questions": [
            _item("公司主营业务与收入结构是什么？各板块增速如何？", "high"),
            _item("行业整体景气度与公司在行业中的竞争位置如何？", "high"),
            _item("近三年营收、利润、现金流与 ROE 的趋势如何？", "high"),
            _item("当前估值（PE/PB/PS）处于历史与同业什么水平？", "medium"),
            _item("主要风险因素有哪些（政策、竞争、财务质量）？", "medium"),
        ],
        "analysis_dimensions": ["商业模式", "行业与竞争", "财务质量", "估值", "风险"],
        "data_requirements": ["近三年财报", "行业研报", "同业估值对比", "公司公告"],
        "suggested_sources": ["年报/季报", "券商研报", "行业统计", "交易所公告"],
    },
    "earnings": {
        "research_goal": "点评最新一期财报：业绩是否超/低预期，趋势是否延续",
        "sub_questions": [
            _item("本季营收与净利润同比/环比变化及驱动因素？", "high"),
            _item("毛利率与费用率变化说明什么？", "high"),
            _item("管理层对下季/全年的指引是否可信？", "medium"),
            _item("与此前研究结论对比，趋势是强化还是拐点？", "medium"),
        ],
        "analysis_dimensions": ["业绩对比", "盈利能力", "指引可信度", "趋势延续性"],
        "data_requirements": ["本期财报", "业绩说明会纪要", "此前研究结论"],
        "suggested_sources": ["定期报告", "业绩发布会纪要", "券商点评"],
    },
    "thesis_check": {
        "research_goal": "检验既有投资论点：哪些被证实、哪些被动摇",
        "sub_questions": [
            _item("当初买入论点的关键假设，近期数据是否支持？", "high"),
            _item("出现哪些与论点相悖的新证据？", "high"),
            _item("论点失效的触发条件目前是否已触发？", "medium"),
            _item("论点仍成立的话，加仓/持有的理由是否充分？", "low"),
        ],
        "analysis_dimensions": ["假设验证", "反面证据", "失效条件", "持仓决策"],
        "data_requirements": ["最新财务数据", "相关新闻与公告", "原始研究记录"],
        "suggested_sources": ["定期报告", "新闻检索", "历史研究时间线"],
    },
    "industry": {
        "research_goal": "行业对比：标的公司相对同业的优劣势与估值差",
        "sub_questions": [
            _item("行业内主要玩家的市占率与增长对比如何？", "high"),
            _item("标的公司的差异化优势（成本/技术/渠道）是否可持续？", "high"),
            _item("同业估值倍数对比，溢价/折价的合理性？", "medium"),
            _item("行业政策与周期位置对格局的影响？", "medium"),
        ],
        "analysis_dimensions": ["竞争格局", "比较优势", "估值对比", "政策与周期"],
        "data_requirements": ["同业财务数据", "行业集中度数据", "政策文件"],
        "suggested_sources": ["行业研报", "同业年报", "行业协会统计"],
    },
}


class ResearchPlanner:
    """Generates structured research plans from questions using LLM."""

    def __init__(self, llm: LLM | None = None) -> None:
        self.llm = llm or create_llm()

    async def generate_plan(
        self,
        question: str,
        context: str | None = None,
        company_name: str | None = None,
        plan_type: str | None = None,
    ) -> dict:
        """生成研究计划：plan_type 命中模板直接返回（零 LLM 调用），否则 LLM 生成。

        LLM 失败时兜底用 initial 模板（此前是硬编码英文 fallback，现统一为模板）。
        """
        if plan_type and plan_type in PLAN_TEMPLATES:
            return self._plan_from_template(PLAN_TEMPLATES[plan_type], question, company_name)

        user_prompt = f"Research Question: {question}\n"
        if context:
            user_prompt += f"Context: {context}\n"
        if company_name:
            user_prompt += f"Company: {company_name}\n"

        user_prompt += (
            "\nCreate a detailed research plan as JSON with keys: "
            "research_goal, sub_questions (list of objects with id/text/priority/status), "
            "analysis_dimensions (list), data_requirements (list), suggested_sources (list)."
        )

        messages = [
            LLMMessage(role="system", content=RESEARCH_PLAN_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]

        try:
            response = await self.llm.generate(
                messages=messages,
                temperature=0.3,
                max_tokens=2048,
            )
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("```", 1)[0]
            if content.startswith("json"):
                content = content[4:].strip()
            plan = json.loads(content)
        except (json.JSONDecodeError, AttributeError):
            logger.warning("LLM plan generation failed, falling back to 'initial' template")
            return self._plan_from_template(PLAN_TEMPLATES["initial"], question, company_name)

        # Transform sub_questions to ResearchPlanItem format
        raw_sq = plan.get("sub_questions", [])
        if raw_sq and isinstance(raw_sq, list) and isinstance(raw_sq[0], str):
            # Old format: just strings
            plan["sub_questions"] = [
                {
                    "id": str(uuid4())[:8],
                    "text": q,
                    "priority": "medium",
                    "status": "pending",
                }
                for q in raw_sq
            ]
        elif raw_sq and isinstance(raw_sq, list) and isinstance(raw_sq[0], dict):
            # New format or partially filled - ensure required fields
            enriched: list[dict] = []
            for sq in raw_sq:
                enriched.append(
                    {
                        "id": sq.get("id", str(uuid4())[:8]),
                        "text": sq.get("text", ""),
                        "priority": sq.get("priority", "medium"),
                        "status": sq.get("status", "pending"),
                    }
                )
            plan["sub_questions"] = enriched

        # Ensure required fields with defaults
        plan.setdefault("research_goal", question)
        plan.setdefault("data_requirements", plan.get("data_requirements", []))
        plan.setdefault("suggested_sources", plan.get("suggested_sources", []))
        plan.setdefault("version", plan.get("version", 1))
        plan.setdefault("created_at", plan.get("created_at", datetime.now().isoformat()))

        return plan

    @staticmethod
    def _plan_from_template(
        template: dict, question: str, company_name: str | None
    ) -> dict:
        """从预置模板生成计划：深拷贝、重生成 item id、按问题填充目标句。"""
        import copy

        plan = copy.deepcopy(template)
        subject = f"{company_name}（{question}）" if company_name else question
        plan["research_goal"] = f"{template['research_goal']} — {subject}"
        plan["version"] = 1
        plan["created_at"] = datetime.now().isoformat()
        return plan

    async def generate_structured_thesis(
        self, thesis: str, decision: str, report_content: str
    ) -> dict:
        """Extract structured thesis fields via LLM."""
        prompt = f"""Based on this investment thesis and report, extract as JSON:
{{"bull_case": ["..."], "bear_case": ["..."], "key_drivers": ["..."], "risks": ["..."]}}

Decision: {decision}
Thesis: {thesis[:1500]}
Report: {report_content[:3000]}"""

        try:
            response = await self.llm.generate(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.3,
                max_tokens=1024,
            )
            result = json.loads(response.content)
            for key in ("bull_case", "bear_case", "key_drivers", "risks"):
                if key not in result or not isinstance(result[key], list):
                    result[key] = []
            return result
        except Exception:
            logger.warning("LLM structured thesis extraction failed, using fallback")
            return {
                "bull_case": [thesis[:200]] if thesis else [],
                "bear_case": [],
                "key_drivers": [],
                "risks": [],
            }
