import os
from dotenv import load_dotenv
from typing import Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core.base_tools import ALL_TOOLS, KBS
from core.models import KnowledgeBase

load_dotenv()

def create_model():
    return ChatOpenAI(
        model="openai/gpt-4o",  # or a specific openrouter model like openai/gpt-4o-mini
        temperature=0.6,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    ).bind_tools(ALL_TOOLS)


def _build_symptom_summary(kb: KnowledgeBase) -> str:
    """Формирует краткий список симптомов из базы знаний для промпта."""
    lines = []
    for s in kb.symptoms:
        lines.append(f"  {s.code}. [{s.id}] {s.title}")
        for c in s.possible_causes:
            prob_pct = int(c.prior_probability * 100)
            lines.append(f"     → [{c.id}] {c.title} (вер.~{prob_pct}%, серьёзн.: {c.severity.value})")
    return "\\n".join(lines)


def get_system_prompt(service_id: str, kb: KnowledgeBase) -> str:
    skill_path = os.path.join(os.getcwd(), ".agents", "skills", service_id, "SKILL.md")
    skill_content = ""
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            skill_content = f.read()
    except FileNotFoundError:
        skill_content = f"Ты — технический специалист направления {service_id.upper()}."

    return f"""ОБЯЗАТЕЛЬНО передавай service="{service_id}" во все вызовы инструментов (tools).

{skill_content}

# БАЗА ЗНАНИЙ (СИМПТОМЫ И ПРИЧИНЫ):
{_build_symptom_summary(kb)}

# КАК РАБОТАТЬ С TOOLS (СТРОГИЕ ДИРЕКТИВЫ):

1. Ты MUST вызывать update_diagnosis СРАЗУ как жилец сообщил что-то информативное: подтверждённые/опровергнутые факторы, масштаб проблемы.
2. Ты MUST вызывать get_causes_ranked после update_diagnosis чтобы узнать текущий рейтинг причин.
3. Ты MUST вызывать get_next_question когда нужен следующий уточняющий вопрос.
4. Ты MUST вызывать create_ticket когда причина установлена и нужен выход мастера, или жилец требует этого.
5. Ты MUST вызывать explain_cause для финального объяснения жильцу.

ПОРЯДОК ДИАГНОСТИКИ (MUST FOLLOW):
Шаг 1: Выяснить базовую картину.
Шаг 2: update_diagnosis с первичными факторами.
Шаг 3: get_causes_ranked.
Шаг 4: get_next_question (задавать строго ОДИН вопрос).
Шаг 5: Повторять 2-4 пока не наберётся уверенность.
Шаг 6: explain_cause + create_ticket если нужен мастер.

ВАЖНО: Ты MUST NOT ставить диагноз без достаточных данных.
"""

class AgentState(BaseModel):
    messages: Annotated[list, add_messages] = Field(default_factory=list)

def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    last = state.messages[-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "__end__"

def build_service_agent(service_id: str):
    kb = KBS.get(service_id)
    if not kb:
        raise ValueError(f"KnowledgeBase for {service_id} not found")

    system_prompt = get_system_prompt(service_id, kb)

    def agent_node(state: AgentState) -> dict:
        model = create_model()
        messages = [SystemMessage(content=system_prompt)] + state.messages
        response = model.invoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(ALL_TOOLS)
    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("agent", agent_node)
    graph_builder.add_node("tools", tool_node)

    graph_builder.add_edge(START, "agent")
    graph_builder.add_conditional_edges("agent", should_continue)
    graph_builder.add_edge("tools", "agent")

    memory = MemorySaver()
    return graph_builder.compile(checkpointer=memory)
