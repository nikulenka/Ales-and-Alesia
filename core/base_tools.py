"""
tools.py — LangChain tools для агента Алесь

Каждый tool — это действие, которое агент может вызвать структурированно.
Все входные/выходные данные типизированы через Pydantic.

Tools:
  1. update_diagnosis   — обновить текущую диагностическую сессию
  2. get_causes_ranked  — получить отранжированные причины по подтверждённым факторам
  3. get_next_question  — получить следующий диагностический вопрос
  4. create_ticket      — создать заявку диспетчеру/мастеру
  5. explain_cause      — сформировать понятное объяснение причины для жильца
"""

from __future__ import annotations
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from core.models import DiagnosisSession, TemperatureLevel, Severity
from core.kb_loader import load_all_kbs

KBS = load_all_kbs()


# ══════════════════════════════════════════════
# Tool 1: Обновление диагностической сессии
# ══════════════════════════════════════════════

class UpdateDiagnosisInput(BaseModel):
    """Входные данные для обновления диагностической сессии."""
    service: str = Field(description="ID сервиса (напр. 'hvs', 'heating')")
    confirmed_factor_ids: list[str] = Field(
        default_factory=list,
        description="ID факторов (ObservableFactor или SecondaryFactor), которые жилец только что подтвердил"
    )
    ruled_out_factor_ids: list[str] = Field(
        default_factory=list,
        description="ID факторов, которые жилец опроверг"
    )
    hot_tap_temp: Optional[TemperatureLevel] = Field(
        default=None,
        description="Уровень температуры в горячем кране, если жилец его описал"
    )
    scope_is_building: Optional[bool] = Field(
        default=None,
        description="True если проблема у дома/стояка, False если только в квартире"
    )
    suspected_symptom_id: Optional[str] = Field(
        default=None,
        description="ID симптома, если уже удалось определить"
    )


class UpdateDiagnosisOutput(BaseModel):
    session: DiagnosisSession
    message: str


@tool("update_diagnosis", args_schema=UpdateDiagnosisInput)
def update_diagnosis(
    service: str,
    confirmed_factor_ids: list[str],
    ruled_out_factor_ids: list[str],
    hot_tap_temp: Optional[TemperatureLevel],
    scope_is_building: Optional[bool],
    suspected_symptom_id: Optional[str],
) -> dict:
    """Обновляет диагностическую сессию на основе новых данных от жильца.
    Вызывай после каждого информативного ответа жильца.
    """
    session = DiagnosisSession(
        confirmed_factors=confirmed_factor_ids,
        ruled_out_factors=ruled_out_factor_ids,
        hot_tap_temp=hot_tap_temp,
        scope_is_building=scope_is_building,
        suspected_symptom_id=suspected_symptom_id,
    )
    return {
        "session": session.model_dump(),
        "message": f"Сессия обновлена: подтверждено {len(confirmed_factor_ids)} факторов, исключено {len(ruled_out_factor_ids)}"
    }


# ══════════════════════════════════════════════
# Tool 2: Ранжирование причин
# ══════════════════════════════════════════════

class CauseScore(BaseModel):
    cause_id: str
    title: str
    category: str
    score: float = Field(description="Итоговая вероятность после учёта подтверждённых факторов")
    severity: Severity
    resolution: str
    note: Optional[str] = None


class GetCausesRankedInput(BaseModel):
    service: str = Field(description="ID сервиса")
    symptom_id: str = Field(description="ID симптома из базы знаний")
    confirmed_factor_ids: list[str] = Field(default_factory=list)
    ruled_out_factor_ids: list[str] = Field(default_factory=list)


@tool("get_causes_ranked", args_schema=GetCausesRankedInput)
def get_causes_ranked(
    service: str,
    symptom_id: str,
    confirmed_factor_ids: list[str],
    ruled_out_factor_ids: list[str],
) -> dict:
    """Возвращает причины для симптома, отранжированные по вероятности с учётом подтверждённых факторов.
    Используй для выбора следующего вопроса или итоговой рекомендации.
    """
    kb = KBS.get(service)
    if not kb:
        return {"error": f"Сервис {service} не найден"}
    
    symptom = kb.get_symptom(symptom_id)
    if not symptom:
        return {"error": f"Симптом {symptom_id} не найден в базе знаний"}

    scored: list[CauseScore] = []
    for cause in symptom.possible_causes:
        score = cause.prior_probability

        # Подтверждающие факторы поднимают вероятность
        for fid in confirmed_factor_ids:
            if fid in cause.confirming_factors:
                score = min(1.0, score * 1.6)

        # Исключающие факторы снижают вероятность
        for fid in ruled_out_factor_ids:
            if fid in cause.ruling_out_factors:
                score *= 0.05  # практически исключаем

        # Явные противоречия
        for fid in confirmed_factor_ids:
            if fid in cause.ruling_out_factors:
                score *= 0.1

        scored.append(CauseScore(
            cause_id=cause.id,
            title=cause.title,
            category=cause.category,
            score=round(score, 3),
            severity=cause.severity,
            resolution=cause.resolution,
            note=cause.note,
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return {"ranked_causes": [c.model_dump() for c in scored]}


# ══════════════════════════════════════════════
# Tool 3: Следующий диагностический вопрос
# ══════════════════════════════════════════════

class GetNextQuestionInput(BaseModel):
    service: str = Field(description="ID сервиса")
    symptom_id: str = Field(description="ID симптома")
    already_asked_factor_ids: list[str] = Field(
        default_factory=list,
        description="ID факторов, по которым вопрос уже задавался"
    )
    top_cause_ids: list[str] = Field(
        default_factory=list,
        description="ID топ-причин (из get_causes_ranked) — вопросы по ним приоритетны"
    )


class NextQuestionOutput(BaseModel):
    factor_id: str
    question: str
    rationale: str


@tool("get_next_question", args_schema=GetNextQuestionInput)
def get_next_question(
    service: str,
    symptom_id: str,
    already_asked_factor_ids: list[str],
    top_cause_ids: list[str],
) -> dict:
    """Возвращает следующий диагностический вопрос, который стоит задать жильцу.
    Приоритизирует вопросы, различающие топ-причины.
    """
    kb = KBS.get(service)
    if not kb:
        return {"error": f"Сервис {service} не найден"}
        
    symptom = kb.get_symptom(symptom_id)
    if not symptom:
        return {"error": f"Симптом {symptom_id} не найден"}

    # Собираем вторичные факторы, которые ещё не задавались
    unanswered = [
        sf for sf in symptom.secondary_factors
        if sf.id not in already_asked_factor_ids
    ]
    if not unanswered:
        return {"message": "Все уточняющие вопросы уже заданы", "factor_id": None}

    # Приоритизируем: факторы, которые различают топ-причины
    def factor_priority(sf):
        for cause in symptom.possible_causes:
            if cause.id in top_cause_ids:
                if sf.id in cause.confirming_factors or sf.id in cause.ruling_out_factors:
                    return 0  # высокий приоритет
        return 1

    unanswered.sort(key=factor_priority)
    best = unanswered[0]

    return NextQuestionOutput(
        factor_id=best.id,
        question=best.eliciting_question,
        rationale=best.note or "Помогает уточнить причину",
    ).model_dump()


# ══════════════════════════════════════════════
# Tool 4: Создание заявки
# ══════════════════════════════════════════════

class CreateTicketInput(BaseModel):
    service: str = Field(description="ID сервиса")
    tenant_address: str = Field(description="ВАЖНО: Точный адрес жильца.ЗАПРЕЩЕНО выдумывать! Если жилец ещё не назвал адрес, ОБЯЗАТЕЛЬНО сначала спроси его.")
    tenant_phone: str = Field(description="ВАЖНО: Номер телефона жильца. ЗАПРЕЩЕНО выдумывать! Если жилец ещё не назвал телефон, ОБЯЗАТЕЛЬНО сначала спроси его.")
    symptom_id: Optional[str] = Field(default=None, description="ID установленного симптома")
    top_cause_id: Optional[str] = Field(default=None, description="ID наиболее вероятной причины")
    urgency: Literal["emergency", "urgent", "normal"] = Field(
        default="normal",
        description="emergency=авария, urgent=горячей нет совсем, normal=дискомфорт"
    )
    notes: str = Field(default="", description="Дополнительные заметки агента")


class TicketOutput(BaseModel):
    ticket_id: str
    summary: str
    urgency: str
    assignee: str
    resident_message: str


@tool("create_ticket", args_schema=CreateTicketInput)
def create_ticket(
    service: str,
    apartment_info: str,
    symptom_id: Optional[str],
    top_cause_id: Optional[str],
    urgency: str,
    notes: str,
) -> dict:
    """Создаёт заявку диспетчеру или мастеру.
    Вызывай когда диагноз поставлен или проблема требует выхода специалиста.
    """
    import uuid, datetime

    kb = KBS.get(service)
    symptom = kb.get_symptom(symptom_id) if kb and symptom_id else None
    cause_title = ""
    if symptom and top_cause_id:
        cause = next((c for c in symptom.possible_causes if c.id == top_cause_id), None)
        cause_title = cause.title if cause else top_cause_id

    ticket_id = f"TKT-{datetime.date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"

    assignees = {
        "emergency": "Аварийная служба (немедленно)",
        "urgent": "Дежурный слесарь ИТП",
        "normal": "Слесарь-сантехник (плановый выход)",
    }

    summary = f"[ГВС] {symptom.title if symptom else 'Проблема с горячей водой'}"
    if cause_title:
        summary += f" — предв. причина: {cause_title}"

    resident_msg_map = {
        "emergency": "Заявка передана в аварийную службу. Специалист выедет в течение 1 часа.",
        "urgent": "Заявка зарегистрирована. Дежурный слесарь займётся сегодня.",
        "normal": "Заявка принята. Мастер придёт в ближайший рабочий день — вам позвонят.",
    }

    ticket = TicketOutput(
        ticket_id=ticket_id,
        tenant_address=tenant_address,
        tenant_phone=tenant_phone,
        summary=summary,
        urgency=urgency,
        assignee=assignees[urgency],
        resident_message=resident_msg_map[urgency],
    )
    return ticket.model_dump()


# ══════════════════════════════════════════════
# Tool 5: Объяснение причины жильцу
# ══════════════════════════════════════════════

class ExplainCauseInput(BaseModel):
    service: str = Field(description="ID сервиса")
    cause_id: str = Field(description="ID причины из базы знаний")
    symptom_id: str = Field(description="ID симптома")


@tool("explain_cause", args_schema=ExplainCauseInput)
def explain_cause(service: str, cause_id: str, symptom_id: str) -> dict:
    """Возвращает понятное объяснение причины и следующие шаги для жильца.
    Используй для финального сообщения когда причина установлена.
    """
    kb = KBS.get(service)
    if not kb:
        return {"error": f"Сервис {service} не найден"}
        
    symptom = kb.get_symptom(symptom_id)
    if not symptom:
        return {"error": f"Симптом {symptom_id} не найден"}

    cause = next((c for c in symptom.possible_causes if c.id == cause_id), None)
    if not cause:
        return {"error": f"Причина {cause_id} не найдена в симптоме {symptom_id}"}

    return {
        "cause_title": cause.title,
        "explanation": cause.description,
        "plain_language_note": cause.note,
        "severity": cause.severity.value,
        "resolution": cause.resolution,
        "category": cause.category,
    }


# ══════════════════════════════════════════════
# Экспорт списка tools
# ══════════════════════════════════════════════

ALL_TOOLS = [
    update_diagnosis,
    get_causes_ranked,
    get_next_question,
    create_ticket,
    explain_cause,
]
