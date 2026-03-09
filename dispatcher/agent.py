from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from core.base_agent import create_model
from core.models import DispatchResult

DISPATCHER_PROMPT = """Ты — интеллектуальный маршрутизатор (Диспетчер) заявок в службе ЖКХ.
Твоя задача — проанализировать сообщение жильца и определить, в какую службу его направить.

Доступные службы:
- hvs: Горячее водоснабжение (недостаточная температура воды горячего стояка)
- heating: Отопление (холодные батареи, трубы отопления)
- cold_water: Холодное водоснабжение и канализация (нет воды, засоры, протечки холодной воды)
- electricity: Электричество (нет света, искрит розетка, выбивает автоматы)

Если уверен в выборе (confidence >= 0.7), заявка будет направлена специалисту.
Если нет, можешь задать уточняющий вопрос или направить на диспетчера-человека, вернув null/None в service.
"""

def route_query(user_message: str) -> DispatchResult:
    """Определяет, к какому сервису относится запрос."""
    # Используем with_structured_output для получения строгого ответа Pydantic
    model = create_model().bind_tools([]) # снимаем tools, если они были привязаны по умолчанию
    structured_model = model.with_structured_output(DispatchResult)
    
    messages = [
        SystemMessage(content=DISPATCHER_PROMPT),
        HumanMessage(content=user_message)
    ]
    
    result = structured_model.invoke(messages)
    return result
