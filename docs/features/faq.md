# Feature: faq

## Goal
Отвечать на вопросы пользователя о работе сервиса (оформление заказа, график, возможности приложения) через семантический поиск по FAQ-чанкам.

## User Flow
1. Пользователь задает вопрос ассистенту.
2. LLM выбирает MCP tool `support_knowledge_search` по описанию.
3. Сервер строит embedding через OpenAI `text-embedding-3-small` (`1536`).
4. Вектор отправляется в Supabase RPC-функцию для поиска по `faq_chunks`.
5. Возвращаются релевантные чанки для финального ответа пользователю.

## Inputs/Outputs
- Inputs:
  - `query: string` - текст вопроса.
  - `limit?: integer` - максимальное число FAQ-чанков.
- Outputs:
  - `query: string` - нормализованный запрос.
  - `count: integer` - число найденных чанков.
  - `chunks: array<object>` - найденные чанки из Supabase.

## Dependencies
- OpenAI Embeddings API (`text-embedding-3-small`).
- Supabase REST RPC endpoint `/rest/v1/rpc/<function_name>`.
- Переменные окружения:
  - `OPENAI_API_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_KEY` (приоритетно)
  - `SUPABASE_SERVICE_ROLE_KEY` (fallback для совместимости)
  - `FAQ_EMBEDDING_DIMENSIONS` (размер embeddings, по умолчанию `1536`)
  - `FAQ_MATCH_COUNT_DEFAULT` (число чанков по умолчанию, по умолчанию `5`)
  - `FAQ_MATCH_THRESHOLD` (порог similarity для RPC-функции)
  - Используется фиксированная RPC-функция `match_faq_chunks`

## Edge Cases
- Пустой `query` -> валидационная ошибка.
- Не настроены ключи/URL -> ошибка конфигурации.
- Supabase RPC вернул не-массив -> пустой результат.

## Test Cases
- Unit:
  - Валидация пустого запроса.
  - Проверка формирования payload для OpenAI embeddings.
  - Проверка payload и headers для Supabase RPC.
- Integration:
  - Делегирование из MCP registry в `support_knowledge_search`.
- E2E:
  - Smoke через MCP `tools/list` и `tools/call`.

## Tech Debt / Next Improvements
- Добавить fallback-модель embedding при временной недоступности API.
- Добавить пост-обработку чанков (дедупликация/порог релевантности).
- Поддержать фильтры по языку и категории FAQ.
