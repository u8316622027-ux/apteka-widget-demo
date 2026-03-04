# Frontend Standards

## Scope
Эти правила описывают базовый стандарт для UI-виджетов в `app/widgets/*`.

## Rules
1. `No inline CSS/JS`
   - Большие блоки `<style>` и `<script>` в `.html` запрещены.
   - Допустимо до 5 строк с пояснением причины и задачей на вынос.
2. `Styles location + naming`
   - Стили храним в `app/widgets/styles/`.
   - Формат: `widget-<name>.css` (пример: `widget-products.css`) или секция в общем файле с префиксом фичи.
3. `CSS load order`
   - Порядок подключения: `tokens.css -> base.css -> widget-shell.css -> widget-*.css`.
4. `Design tokens first`
   - Цвета, spacing, radius, typography и breakpoints берутся из токенов.
   - Хардкод только для прототипа и удаляется до merge.
5. `Scoped naming`
   - Классы и data-атрибуты именуем с префиксом фичи: `products-*`, `checkout-*`, `tracking-*`.
6. `Responsive baseline`
   - Обязательная проверка UI на `320px`, `768px`, `1280px`.
7. `Layout ownership`
   - Глобальные стили (`html`, `body`, shell) задаются в базовых стилях.
   - Виджетные стили не должны менять глобальный layout.
8. `Alpine.js conventions`
   - `x-data` только на корневом элементе виджета.
   - Состояние/методы именуются по фиче.
   - Alpine не используем для полностью статичных блоков.
9. `Accessibility minimum`
   - Обязательны `aria-label` для icon-only кнопок, видимый `:focus`, достаточный контраст, семантические теги, клавиатурная навигация.
10. `DOM stability for tests`
   - Ключевые элементы имеют стабильные селекторы (`data-testid` или фича-классы).
11. `UI testing policy`
   - Для bugfix изменений обязателен TDD: `Red -> Green -> Refactor`.
   - Для новых экранов допускается прототипирование, но тесты обязательны до merge.
12. `No dead CSS`
   - Минимум: ручная проверка через DevTools Coverage на измененном экране.
   - При наличии build-step используем автоматический purge/treeshaking.
13. `Dependency gate`
   - Новая фронтенд-зависимость добавляется только с короткой записью решения в `docs/frontend/decisions/`.
14. `Definition of Done`
   - Пройдены quality gates.
   - Сделана визуальная проверка на `320px`, `768px`, `1280px`.
   - В PR описано: что изменено, какие тесты добавлены, какие селекторы зафиксированы.
