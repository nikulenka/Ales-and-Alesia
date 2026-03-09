import streamlit as st
import uuid
import os
from langchain_core.messages import HumanMessage, AIMessage
from core.models import DispatchResult

from dispatcher.agent import route_query
from core.base_agent import build_service_agent

st.set_page_config(page_title="Алесь & Алеся — ЖКУ-агенты", page_icon="🏢", layout="wide")

# Настройка сессии
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "service" not in st.session_state:
    st.session_state.service = None  # ServiceType.value
if "agents" not in st.session_state:
    st.session_state.agents = {}  # кэш скомпилированных графов

def get_agent(service_id: str):
    if service_id not in st.session_state.agents:
        try:
            st.session_state.agents[service_id] = build_service_agent(service_id)
        except Exception as e:
            st.error(f"Ошибка загрузки базы знаний для сервиса {service_id}: {e}")
            return None
    return st.session_state.agents[service_id]

# UI Header
st.title("📞 Платформа ЖКУ-агентов (Алесь & Алеся)")
if st.session_state.service:
    st.info(f"Текущая служба: **{st.session_state.service.upper()}** (Маршрутизация завершена)")
else:
    st.warning("Маршрутизация: **Диспетчер** (Определяю профиль проблемы...)")

if st.button("Сбросить диалог"):
    st.session_state.messages = []
    st.session_state.service = None
    st.session_state.session_id = str(uuid.uuid4())
    st.rerun()

# Отображение истории
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.write(msg["content"])
    else:
        with st.chat_message("assistant"):
            st.write(msg["content"])
            if msg.get("tools"):
                with st.expander("Технические детали (Tool Calls)", expanded=False):
                    for tool in msg["tools"]:
                        st.code(f"{tool['name']}({tool['args']})")

# Ввод пользователя
user_input = st.chat_input("Опишите вашу проблему с водоснабжением, отоплением или электричеством...")

if user_input:
    # 1. Сразу выводим сообщение пользователя
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        tools_placeholder = st.empty()
        
        # 1. Если сервис ещё не определён — работает Диспетчер
        if not st.session_state.service:
            with st.spinner("Диспетчер анализирует..."):
                dispatch_result: DispatchResult = route_query(user_input)
                
            if dispatch_result.service and dispatch_result.confidence >= 0.7:
                st.session_state.service = dispatch_result.service.value
                st.success(f"Диспетчер передаёт заявку в службу: {st.session_state.service.upper()} ({dispatch_result.reasoning})")
            else:
                # Диспетчер не смог маршрутизировать уверенно
                msg = f"Пожалуйста, уточните вашу проблему. {dispatch_result.reasoning}"
                st.session_state.messages.append({"role": "assistant", "content": msg})
                message_placeholder.markdown(msg)
                st.stop()

        # 2. Сервис определён — работает специализированный Агент
        agent = get_agent(st.session_state.service)
        if not agent:
            st.stop()

        config = {"configurable": {"thread_id": st.session_state.session_id}}
        
        with st.spinner(f"Специалист службы {st.session_state.service.upper()} работает..."):
            # Формируем историю для LangGraph агента
            history = []
            for m in st.session_state.messages:
                if m["role"] == "user":
                    history.append(HumanMessage(content=m["content"]))
                else:
                    # Упрощённо, не передавая полные ToolMessage обратно, только AIMessage
                    history.append(AIMessage(content=m["content"]))
                    
            # Добавим последнее сообщение (уже есть в history, но мы можем просто подать его в invoke)
            # В invoke подаём только то, что отправляем сейчас, history возьмётся из памяти MemorySaver
            # НО мы не сохраняли в MemorySaver вручную! MemorySaver работает сам, если мы шлём в него invoke.
            # Для простоты шлём только последнее сообщение:
            result = agent.invoke({"messages": [HumanMessage(content=user_input)]}, config)
            
            # Извлекаем финальный ответ и тул-коллы
            ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
            final_msg = ai_msgs[-1].content
            
            tool_calls_info = []
            for m in ai_msgs:
                if hasattr(m, 'tool_calls') and m.tool_calls:
                    for tc in m.tool_calls:
                        tool_calls_info.append({"name": tc["name"], "args": tc["args"]})

            message_placeholder.markdown(final_msg)
            if tool_calls_info:
                with tools_placeholder.expander("Технические детали (Tool Calls)", expanded=False):
                    for tc in tool_calls_info:
                        st.code(f"{tc['name']}({tc['args']})")

            st.session_state.messages.append({
                "role": "assistant",
                "content": final_msg,
                "tools": tool_calls_info
            })
