# 🏢 Платформа ЖКУ-агентов v2

LangGraph + LangChain + Pydantic. Диспетчер + 4 специализированных агента.
Базы знаний — в YAML, редактируются специалистами без кода.

---

## Быстрый старт

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
python app.py
```

---

## Структура

```
jku_platform/
│
├── app.py                        # Точка входа: загрузка + запуск
│
├── core/                         # Общее ядро — не трогать специалистам
│   ├── models.py                 # Все Pydantic-модели платформы
│   ├── kb_loader.py              # Загрузка YAML → Pydantic + валидация
│   ├── base_tools.py             # 5 общих tools для всех агентов
│   └── base_agent.py             # Фабрика: build_service_agent(kb)
│
├── dispatcher/
│   └── agent.py                  # Агент-диспетчер: определяет тему → маршрутизирует
│
└── services/
    ├── hvs/kb/knowledge_base.yaml         # ГВС ← редактирует специалист ГВС
    ├── heating/kb/knowledge_base.yaml     # Отопление ← редактирует теплотехник
    ├── cold_water/kb/knowledge_base.yaml  # ХВС/Канализация ← редактирует сантехник
    └── electricity/kb/knowledge_base.yaml # Электричество ← редактирует электрик
```

---

## Как добавить новый сервис

1. Создать папку `services/my_service/kb/`
2. Скопировать любой `knowledge_base.yaml` как шаблон
3. Заполнить симптомы и причины
4. Добавить `ServiceType.MY_SERVICE = "my_service"` в `core/models.py`
5. Всё — `load_all_kbs()` подхватит автоматически

---

## Как редактировать базу знаний (для специалистов ЖКУ)

Откройте файл `services/<сервис>/kb/knowledge_base.yaml`.

**Структура причины:**
```yaml
- id: C_UNIQUE_ID          # уникальный код (латиница, без пробелов)
  category: building_itp   # external/building_itp/riser/apartment/neighbor
  title: Краткое название
  description: Подробное описание механизма
  note: Объяснение жильцу простым языком (необязательно)
  prior_probability: 0.35  # ваша оценка: 0.0 (редко) .. 1.0 (почти всегда)
  severity: high           # critical/high/medium/low
  confirming_factors: [SF_ID1, SF_ID2]   # ID факторов которые подтверждают
  ruling_out_factors: [SF_ID3]           # ID факторов которые исключают
  resolution: Что делать агенту/диспетчеру
```

**После правок** установите:
```yaml
reviewed_by_expert: true
expert_name: Иванов И.И.
```

**Проверка синтаксиса:**
```bash
python -c "from core.kb_loader import load_kb; load_kb('services/hvs/kb/knowledge_base.yaml')"
```

---

## Архитектура маршрутизации

```
Жилец: "у меня холодные батареи"
            │
            ▼
    [Диспетчер-агент]
    route_to_service(service="heating", confidence=0.95)
            │
            ▼ (confidence >= 0.7)
    [Агент отопления]
    ← build_service_agent(heating_kb) ←
    ← BASE_TOOLS + heating_kb промпт ←
            │
            ▼
    Диагностический диалог
```

---

## Pydantic-модели (core/models.py)

| Модель | Назначение |
|--------|-----------|
| `ServiceType` | Перечисление сервисов (hvs/heating/cold_water/electricity) |
| `Severity` | Серьёзность: critical/high/medium/low |
| `CauseCategory` | Откуда причина: external/building_itp/riser/apartment/neighbor |
| `FactorType` | Тип фактора: primary/secondary/temporal/scope/equipment |
| `ObservableFactor` | Первичный факт — жилец сообщает сам |
| `SecondaryFactor` | Уточняющий факт + `eliciting_question` |
| `DiagnosticAction` | Что попросить жильца сделать |
| `Cause` | Причина: `prior_probability`, `severity`, `confirming/ruling_out_factors` |
| `Symptom` | Симптом: первичные + вторичные факторы + список причин |
| `ServiceKnowledgeBase` | База одного сервиса: симптомы + `reviewed_by_expert` |
| `DiagnosisSession` | Состояние диагностики (заполняет агент) |
| `DispatchResult` | Результат маршрутизации диспетчером |

---

## Tools (core/base_tools.py)

Все 5 tools общие для всех сервисов. Каждый принимает `service: str` — знает к какой KB обращаться.

| Tool | Когда вызывается |
|------|-----------------|
| `update_diagnosis` | После каждого информативного ответа жильца |
| `get_causes_ranked` | После update_diagnosis — ранжирует причины |
| `get_next_question` | Когда нужен следующий уточняющий вопрос |
| `explain_cause` | Финальное объяснение жильцу |
| `create_ticket` | Нужен мастер или жилец просит зарегистрировать |
