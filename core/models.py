"""
models.py — Pydantic-модели предметной области ГВС МКД

Иерархия:
  TemperatureLevel       — шкала температуры воды (субъективная, по ощущениям жильца)
  Severity               — серьёзность проблемы для жильца
  CauseCategory          — категория причины (откуда она «родом»)
  ObservableFactor       — первичный наблюдаемый факт (то, что жилец может сообщить)
  SecondaryFactor        — вторичный/уточняющий фактор (выявляется в ходе диалога)
  DiagnosticAction       — что попросить жильца сделать прямо сейчас
  Cause                  — причина неисправности с вероятностью и серьёзностью
  Symptom                — симптом: набор факторов + список возможных причин
  KnowledgeBase          — вся база знаний, загружается один раз
"""

from __future__ import annotations
from enum import Enum
from typing import Annotated, Optional, Union, Any
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════
# Перечисления (справочники)
# ══════════════════════════════════════════════

class ServiceType(str, Enum):
    HVS = "hvs"
    HEATING = "heating"
    COLD_WATER = "cold_water"
    ELECTRICITY = "electricity"

class TemperatureLevel(str, Enum):
    """Субъективная шкала температуры воды.
    Определяется ТОЛЬКО по ощущениям жильца — без термометра.
    """
    HOT        = "hot"       # Нужно мешать с холодной, иначе обожжёшься
    WARM       = "warm"      # Тёплая: приятная, но для душа мало
    COLD_LIKE  = "cold_like" # Почти как из холодного крана
    NO_WATER   = "no_water"  # Воды нет вообще


class Severity(str, Enum):
    """Серьёзность проблемы с точки зрения комфорта и здоровья жильца."""
    CRITICAL  = "critical"   # Нет воды / кипяток — немедленное вмешательство
    HIGH      = "high"       # Нет горячей — нельзя принять душ
    MEDIUM    = "medium"     # Тёплая вместо горячей — дискомфорт
    LOW       = "low"        # Едва заметное отклонение


class CauseCategory(str, Enum):
    """Откуда «родом» причина неисправности."""
    EXTERNAL      = "external"       # Теплосеть, магистраль — вне дома
    BUILDING_ITP  = "building_itp"   # ИТП / общедомовое оборудование
    RISER         = "riser"          # Стояк / внутридомовая разводка
    APARTMENT     = "apartment"      # Квартира жильца
    NEIGHBOR      = "neighbor"       # Квартира соседа (незаконные переделки и т.п.)
    UNKNOWN       = "unknown"        # Не определена


class FactorType(str, Enum):
    """Тип фактора — для разметки артефактов."""
    PRIMARY    = "primary"    # Первичный: жилец сообщает сам, без вопросов
    SECONDARY  = "secondary"  # Вторичный: выявляется уточняющим вопросом
    TEMPORAL   = "temporal"   # Временной паттерн (когда, как часто)
    SCOPE      = "scope"      # Масштаб (квартира / стояк / дом)
    EQUIPMENT  = "equipment"  # Наличие оборудования (бойлер, полотенцесушитель)


# ══════════════════════════════════════════════
# Факторы
# ══════════════════════════════════════════════

class ObservableFactor(BaseModel):
    """Первичный наблюдаемый факт — то, что жилец сообщает в первой фразе."""
    id: str = Field(..., description="Уникальный код фактора, напр. 'F_COLD_HOT_TAP'")
    type: FactorType = Field(default=FactorType.PRIMARY)
    description: str = Field(..., description="Человекочитаемое описание факта")
    note: Annotated[Optional[str], Field(description="Пояснительный текст для агента")] = None


class SecondaryFactor(BaseModel):
    """Вторичный/уточняющий фактор — выявляется диагностическим вопросом."""
    id: str = Field(..., description="Уникальный код, напр. 'SF_ONLY_IN_APT'")
    type: FactorType = Field(default=FactorType.SECONDARY)
    description: str = Field(..., description="Описание уточняющего признака")
    eliciting_question: str = Field(..., description="Вопрос жильцу, чтобы выяснить этот фактор")
    note: Annotated[Optional[str], Field(description="Пояснительный текст для агента")] = None


class DiagnosticAction(BaseModel):
    """Действие, которое агент просит жильца выполнить прямо сейчас."""
    id: str = Field(..., description="Уникальный код действия, напр. 'DA_OPEN_CLOSE_TAP'")
    instruction: str = Field(..., description="Что именно попросить сделать жильца")
    expected_result: str = Field(..., description="Что мы ожидаем увидеть/услышать")
    note: Annotated[Optional[str], Field(description="Почему это действие информативно")] = None


# ══════════════════════════════════════════════
# Причина
# ══════════════════════════════════════════════

class Cause(BaseModel):
    """Причина неисправности — один узел в таблице симптом→причина."""
    id: str = Field(..., description="Код причины, напр. 'C_E1_BOILER_NO_CHECK_VALVE'")
    category: CauseCategory
    title: str = Field(..., description="Краткое название причины")
    description: str = Field(..., description="Подробное описание механизма")
    note: Annotated[Optional[str], Field(
        description="Пояснительный текст: почему это происходит, аналогия для жильца"
    )] = None

    # Вероятность и серьёзность
    prior_probability: Annotated[float, Field(
        ge=0.0, le=1.0,
        description="Априорная вероятность этой причины (0..1). "
                    "Требует проверки специалистом ГВС МКД."
    )] = 0.5
    severity: Severity = Field(
        default=Severity.HIGH,
        description="Серьёзность для жильца, если причина подтвердится"
    )

    # Что делать
    confirming_factors: list[str] = Field(
        default_factory=list,
        description="ID факторов (ObservableFactor/SecondaryFactor), подтверждающих эту причину"
    )
    ruling_out_factors: list[str] = Field(
        default_factory=list,
        description="ID факторов, исключающих эту причину"
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="ID DiagnosticAction для подтверждения"
    )
    resolution: str = Field(..., description="Что делать агенту/диспетчеру при подтверждении")


# ══════════════════════════════════════════════
# Симптом
# ══════════════════════════════════════════════

class Symptom(BaseModel):
    """Симптом — точка входа в диагностику."""
    id: str = Field(..., description="Код симптома, напр. 'SYM_G_INTERMITTENT'")
    code: str = Field(..., description="Буквенный код для таблицы (А, Б, В ...)")
    title: str = Field(..., description="Краткое название симптома")
    description: str = Field(..., description="Подробное описание симптома")
    note: Annotated[Optional[str], Field(
        description="Пояснительный текст: особенности интерпретации слов жильца"
    )] = None

    # Температура в горячем кране при этом симптоме
    hot_tap_temp: TemperatureLevel
    # Есть ли вообще холодная вода
    cold_water_present: bool = True

    # Связанные факторы и причины
    primary_factors: list[ObservableFactor] = Field(default_factory=list)
    secondary_factors: list[SecondaryFactor] = Field(default_factory=list)
    possible_causes: list[Cause] = Field(default_factory=list)

    # Базовая серьёзность симптома (до уточнения причины)
    default_severity: Severity = Severity.HIGH


# ══════════════════════════════════════════════
# База знаний
# ══════════════════════════════════════════════

class KnowledgeBase(BaseModel):
    """Полная база знаний агента по ГВС МКД.
    Загружается один раз при старте приложения.
    """
    version: str = Field(default="1.0.0")
    reviewed_by_expert: bool = Field(
        default=False,
        description="Флаг: база проверена специалистом ГВС МКД"
    )
    symptoms: list[Symptom] = Field(default_factory=list)

    def get_symptom(self, symptom_id: str) -> Optional[Symptom]:
        return next((s for s in self.symptoms if s.id == symptom_id), None)

    def get_all_causes(self) -> list[Cause]:
        seen, result = set(), []
        for sym in self.symptoms:
            for c in sym.possible_causes:
                if c.id not in seen:
                    seen.add(c.id)
                    result.append(c)
        return result


# ══════════════════════════════════════════════
# Состояние диагностической сессии
# ══════════════════════════════════════════════

class DiagnosisSession(BaseModel):
    """Текущее состояние диагностики в рамках одного обращения.
    Заполняется агентом в ходе диалога и передаётся как structured output в tools.
    """
    confirmed_factors: list[str] = Field(
        default_factory=list,
        description="ID факторов, которые жилец подтвердил"
    )
    ruled_out_factors: list[str] = Field(
        default_factory=list,
        description="ID факторов, которые жилец опроверг"
    )
    suspected_symptom_id: Optional[str] = Field(
        default=None,
        description="ID симптома, на который больше всего похоже"
    )
    top_causes: list[str] = Field(
        default_factory=list,
        description="ID причин, отранжированных по убыванию вероятности (после уточнений)"
    )
    hot_tap_temp: Optional[TemperatureLevel] = Field(
        default=None,
        description="Установленный уровень температуры в горячем кране"
    )
    scope_is_building: Optional[bool] = Field(
        default=None,
        description="True = проблема у всего дома/стояка, False = только квартира"
    )
    needs_dispatch: bool = Field(
        default=False,
        description="Нужно ли передать заявку диспетчеру/мастеру"
    )
    resolution_note: Optional[str] = Field(
        default=None,
        description="Итоговая рекомендация для жильца"
    )

class DispatchResult(BaseModel):
    """Результат маршрутизации диспетчером."""
    service: Optional[ServiceType] = Field(default=None, description="Сервис для маршрутизации")
    confidence: float = Field(default=0.0, description="Уверенность от 0.0 до 1.0")
    reasoning: str = Field(default="", description="Объяснение маршрутизатора")

