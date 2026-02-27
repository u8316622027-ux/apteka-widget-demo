# ROADMAP.md

## 1. Цель
Стабилизировать проект как модульный монолит с понятными границами доменов, предсказуемым TDD-процессом и управляемым размером файлов.

Критерии:
- Каждый функциональный модуль изолирован и документирован.
- Большие файлы декомпозированы (целевой лимит: до 800 строк для code-файлов; для HTML-шаблонов цель - минимизировать логику и выносить в модули).
- Для каждой фичи есть тесты и feature-док.

## 2. Снимок текущего состояния

### 2.1 Текущий стек (фактически в репозитории)
Backend:
- Python 3.12 (виртуальное окружение `.venv`)
- FastAPI/Starlette (HTTP routes)
- MCP `FastMCP` (tool/resource layer)
- Uvicorn (ASGI запуск)
- Httpx (интеграции с внешними API)
- Pydantic + pydantic-settings (конфиг)

Интеграции:
- Apteka Stage API
- OpenAI Embeddings API
- Supabase RPC / REST
- Yandex Maps JS API

Frontend widget:
- Vanilla JavaScript (без bundler)
- HTML + CSS, инжект через `app/mcp/resources.py`
- Модульная структура уже начата в `app/widgets/scripts/{features,ui,api}`

### 2.2 Текущие проблемные зоны по размеру
- `app/widgets/products.html` ~4329 строк
- `app/mcp/tools.py` ~1469 строк
- `app/widgets/scripts/features/checkout-flow.js` ~876 строк

Дополнительно крупные frontend-модули (кандидаты на разбиение):
- `order-tracking.js` ~613
- `checkout-events.js` ~485
- `map-picker.js` ~478
- `cart-core.js` ~414

### 2.3 Тестовый baseline
- В `tests/` сейчас нет исходных `test_*.py` файлов (остались только `__pycache__`).
- E2E Playwright конфигурация в репозитории пока отсутствует.
- Biome/Ruff в проектной конфигурации пока не зафиксированы отдельными config-файлами.

## 3. Целевая архитектура (скелет)

### 3.1 Backend (Python)
Целевая модель: модульный монолит с явными слоями.

```text
app/
  core/
    config.py
    errors.py
    logging.py
  domain/
    cart/
      entities.py
      service.py
      repository.py
    checkout/
      entities.py
      service.py
      validators.py
    products/
      entities.py
      service.py
      repository.py
    faq/
      service.py
      repository.py
    tracking/
      service.py
      repository.py
  application/
    use_cases/
      cart/
      checkout/
      products/
      faq/
      tracking/
  interfaces/
    http/
      routes/
        cart.py
        checkout.py
        tracking.py
    mcp/
      resources.py
      tools/
        cart_tools.py
        checkout_tools.py
        search_tools.py
        faq_tools.py
        tracking_tools.py
  widgets/
    products.html
    scripts/
    styles/
```

Принципы:
- `interfaces/*` не содержит бизнес-логику.
- Бизнес-правила в `domain/*`.
- Оркестрация сценариев в `application/use_cases/*`.
- Внешние интеграции инкапсулировать в `repository/client`-слое.

### 3.2 Frontend widget
Сохраняем подход без bundler (как сейчас), но усиливаем модульность:

```text
app/widgets/
  products.html            # только разметка + placeholders
  scripts/
    app.js
    state.js
    api/
      *.js
    features/
      cart/
      checkout/
      search/
      tracking/
      map/
    ui/
      *.js
    shared/
      constants.js
      formatters.js
      validators.js
  styles/
    base.css
    checkout.css
    confirmation.css
    map-picker.css
    theme.css
```

## 4. Политика размера и декомпозиции
- Hard target: до 800 строк на code-файл.
- Soft target: 200-500 строк на модуль.
- Если файл > 800 строк:
  - выделить подмодули по bounded context,
  - отделить pure helpers от IO,
  - выделить orchestration слой.

Исключения:
- большие статические ассеты/контентные файлы;
- но `products.html` должен уменьшаться за счет выноса скриптов/стилей и шаблонов.

## 5. План миграции (по этапам)

### Этап A - Baseline и quality gates
1. Зафиксировать toolchain:
- Python lint: `ruff`
- JS/CSS: `biome`
- E2E: `playwright`
2. Добавить конфиги и команды запуска в README/скрипты.
3. Восстановить минимальный набор тестов (smoke) до рефакторинга.

### Этап B - Backend decomposition
1. Разделить `app/mcp/tools.py` на модули по фичам:
- `search_tools.py`
- `cart_tools.py`
- `checkout_tools.py`
- `tracking_tools.py`
- `faq_tools.py`
- `shared_context.py` (общие ctx/state helpers)
2. Вынести бизнес-правила checkout/cart из route/tool слоя в domain/application.
3. Накрыть use-cases unit-тестами.

### Этап C - Frontend decomposition
1. Разбить `checkout-flow.js`:
- steps-navigation
- delivery-method
- payment
- review-render
2. Дробить `order-tracking.js`, `map-picker.js`, `cart-core.js` на feature-submodules.
3. `products.html` сократить до shell + semantic sections + placeholders.

### Этап D - Документация и стабилизация
1. Заполнить docs по каждой фиче (шаблон ниже).
2. Добавить архитектурные решения (ADR) для ключевых компромиссов.
3. Подготовить release-checklist и regression-checklist.

## 6. Feature documentation framework
Подготовлен каталог `docs/features/`:
- `_template.md` - единый шаблон
- отдельные файлы на каждую фичу

Для каждой фичи фиксировать:
- цель и user-flow,
- входы/выходы (API/events/state),
- зависимости,
- edge-cases,
- тест-кейсы (unit/integration/e2e),
- техдолг и план улучшений.

## 7. Приоритетный backlog декомпозиции
1. `app/mcp/tools.py` -> split by tools/domains.
2. `app/widgets/scripts/features/checkout-flow.js` -> split by checkout steps.
3. `app/widgets/products.html` -> shell-only HTML.
4. `tests/` -> восстановить базовые unit + e2e smoke.
5. Заполнить `docs/features/*.md` и связать с тестами.

## 8. Определение готовности (Definition of Done)
Задача по рефакторингу считается завершенной, если:
1. Пройден TDD цикл (Red -> Green -> Refactor).
2. Пройдены проверки:
- `npx biome check --apply .`
- `python -m ruff check .`
- `npx playwright test`
3. Обновлен feature-док в `docs/features/`.
4. Нет новых файлов > 800 строк (без обоснованного исключения).
