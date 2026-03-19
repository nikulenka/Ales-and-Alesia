from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from core.base_agent import create_model
from core.models import DispatchResult

import os

AGENT_MD_PATH = os.path.join(os.path.dirname(__file__), "Agent.md")

def get_dispatcher_prompt() -> str:
    with open(AGENT_MD_PATH, "r", encoding="utf-8") as f:
        return f.read()

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

def route_query(messages_history: list[dict]) -> DispatchResult:
    """Определяет, к какому сервису относится запрос, учитывая контекст диалога."""
    model = create_model().bind_tools([])
    structured_model = model.with_structured_output(DispatchResult)
    
    messages = [SystemMessage(content=get_dispatcher_prompt())]
    
    for msg in messages_history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
            
    result = structured_model.invoke(messages)
    return result
