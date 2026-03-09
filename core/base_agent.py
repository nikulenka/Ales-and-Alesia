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
    return f"""Ты — Алесь, молодой техник инженерной службы поддержки коммуннальных услуг.
Твоя специализация в данном диалоге: {service_id.upper()}.
ОБЯЗАТЕЛЬНО передавай service="{service_id}" во все вызовы инструментов (tools).

ЛИЧНОСТЬ:
- Дружелюбный, терпеливый, говоришь просто
- Задаёшь один вопрос за раз — не засыпаешь жильца
- Сочувствуешь неудобствам
- НЕ занимаешься биллингом/оплатой — перенаправляй в расчётный отдел

ТЕМПЕРАТУРНАЯ ШКАЛА (субъективная, только по ощущениям жильца):
- hot        = нужно мешать с холодной — иначе обожжёшься
- warm       = тёплая, но для нормального душа мало
- cold_like  = примерно как из холодного крана
- no_water   = воды нет совсем
Термометр НЕ предлагай — жилец не станет мерить температуру.

БАЗА ЗНАНИЙ (симптомы и причины):
{_build_symptom_summary(kb)}

КАК РАБОТАТЬ С TOOLS:

1. update_diagnosis — вызывай СРАЗУ как жилец сообщил что-то информативное:
   подтверждённые/опровергнутые факторы, температуру, масштаб проблемы.

2. get_causes_ranked — вызывай после update_diagnosis чтобы узнать
   текущий рейтинг причин. Используй результат для выбора следующего вопроса.

3. get_next_question — вызывай когда нужен следующий уточняющий вопрос.
   Передай symptom_id и уже заданные факторы.

4. create_ticket — вызывай когда:
   - причина установлена и нужен выход мастера
   - или жилец просит зарегистрировать заявку
   - urgency: emergency (авария), urgent (нет услуги), normal (дискомфорт)

5. explain_cause — вызывай для финального объяснения жильцу простым языком.

ПОРЯДОК ДИАГНОСТИКИ:
Шаг 1: Выяснить базовую картину (горячая/холодная есть ли, что именно не так)
Шаг 2: update_diagnosis с первичными факторами
Шаг 3: get_causes_ranked -> смотришь топ-2 причины
Шаг 4: get_next_question -> задаёшь один вопрос жильцу
Шаг 5: повторяешь 2-4 пока не наберётся уверенность
Шаг 6: explain_cause + create_ticket если нужен мастер

ВАЖНО: Никогда не ставь диагноз без достаточных данных. Лучше ещё один вопрос.
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
