# CODEMAP_RESTORE.md

## 1. Цель восстановления
Восстановить проект как модульный монолит с предсказуемым качеством релизов, полной тестовой базой и декомпозированным MCP widget без bundler-зависимости.

Итоговые критерии:
- Явные границы доменов backend и frontend.
- Нет новых code-файлов больше 800 строк без явного исключения.
- Для ключевых сценариев есть unit/integration/e2e покрытие.
- Все quality gates стабильны в CI и локально.

## 2. Полный стек проекта

### 2.1 Backend
- Python 3.12 (`.venv`)
- FastAPI/Starlette (HTTP routes)
- MCP `FastMCP` (tools/resources слой)
- Uvicorn (ASGI runtime)
- Httpx (внешние HTTP-интеграции)
- Pydantic + pydantic-settings (валидация и конфиг)

### 2.2 Интеграции
- Apteka Stage API
- OpenAI Embeddings API
- Supabase RPC/REST
- Yandex Maps JS API

### 2.3 Frontend widget
- Vanilla JavaScript (без bundler)
- HTML/CSS ресурсы, инжект через `app/mcp/resources.py`
- Модульная структура: `app/widgets/scripts/{features,ui,api}`

### 2.4 Качество и процессы
- Lint/format Python: `ruff`
- Lint/format JS/CSS: `biome`
- Backend tests: `pytest`
- E2E tests: `playwright`
- Workflow: Conventional Commits + feature/fix/refactor branches от `dev`

## 3. Целевая архитектура

### 3.1 Backend (модульный монолит)
```text
app/
  core/
  domain/
    cart/
    checkout/
    products/
    faq/
    tracking/
  application/
    use_cases/
  interfaces/
    http/routes/
    mcp/resources.py
    mcp/tools/
```

Принципы:
- `interfaces/*` только адаптеры и транспорт.
- Доменные правила в `domain/*`.
- Оркестрация бизнес-сценариев в `application/use_cases/*`.
- Интеграции с внешними API изолированы в repository/client слое.

### 3.2 Frontend widget
```text
app/widgets/
  products.html
  scripts/
    app.js
    state.js
    api/
    features/
    ui/
    shared/
  styles/
```

Принципы:
- `products.html` = shell + placeholders.
- Feature-логика разнесена по модулям в `scripts/features`.
- UI-утилиты и инфраструктурные вещи отделены в `scripts/ui` и `scripts/shared`.
- Интеграция с MCP через один HTML-ресурс: `ui://widget/products.html`.

## 4. Текущее состояние восстановления
- Есть зафиксированный roadmap и frontend split plan.
- Критичные крупные файлы остаются кандидатами на декомпозицию:
  - `app/mcp/tools.py`
  - `app/widgets/products.html`
  - `app/widgets/scripts/features/checkout-flow.js`
- По frontend уже начата экстракция модулей (`cart-*`, `checkout-*`, `map-picker`, `pickup-geo`, `courier-calc`, `ui/*`, `api/*`).
- Тестовая база и конфиги quality gates требуют доведения до полностью рабочей конфигурации.

## 5. План работ по восстановлению

### Phase A: Baseline и quality gates
1. Зафиксировать конфиги `biome`, `ruff`, `pytest`, `playwright`.
2. Добавить команды запуска в `README`/scripts.
3. Восстановить smoke-набор тестов для backend и widget.

### Phase B: Backend decomposition
1. Разбить `app/mcp/tools.py` на:
   - `search_tools.py`, `cart_tools.py`, `checkout_tools.py`, `tracking_tools.py`, `faq_tools.py`, `shared_context.py`.
2. Вынести бизнес-правила checkout/cart в domain/application.
3. Покрыть use-cases unit/integration тестами.

### Phase C: Frontend decomposition
1. Дробить `checkout-flow.js` на подмодули (steps, delivery, payment, review).
2. Продолжить split `order-tracking.js`, `map-picker.js`, `cart-core.js`.
3. Свести `products.html` к shell-only версии.
4. Довести split CSS (`base`, `checkout`, `map-picker`, далее `confirmation`, `theme`).

### Phase D: Документация и стабилизация
1. Заполнить `docs/features/*.md` по шаблону.
2. Добавить ADR по ключевым архитектурным решениям.
3. Сформировать release/regression checklists.

## 6. Обязательные проверки (Definition of Done)
Перед завершением каждой задачи:
```bash
npx biome check --apply .
python -m ruff format .
python -m ruff check .
python -m pytest
npx playwright test
```

Задача завершена только если:
- TDD цикл выполнен (`Red -> Green -> Refactor`);
- все quality gates проходят;
- обновлена соответствующая feature-документация;
- не добавлены новые файлы >800 строк (без обоснования).

## 7. Приоритет на ближайшие итерации
1. Восстановить и стабилизировать тестовый baseline (`pytest` + `playwright` smoke).
2. Завершить decomposition `app/mcp/tools.py`.
3. Довести split `checkout-flow.js` и уменьшить `products.html`.
4. Подвязать docs/features к каждому изменению и тестам.
