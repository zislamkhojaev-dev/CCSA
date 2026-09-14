# Коды ошибок API (Error Codes Matrix)

Все ошибки API возвращаются в едином JSON без стек-трейса:

```json
{
  "error_code": "AUTH_UNAUTHORIZED",
  "message": "Требуется авторизация",
  "trace_id": "a1b2c3d4-..."
}
```

Заголовок ответа `X-Request-ID` совпадает с `trace_id`.

| Код | HTTP | Когда |
|-----|------|--------|
| `AUTH_UNAUTHORIZED` | 401 | Нет или невалидный JWT |
| `AUTH_INVALID_CREDENTIALS` | 401 | Неверный логин/пароль |
| `AUTH_FORBIDDEN` | 403 | Недостаточно прав (RBAC) |
| `AUTH_INACTIVE` | 403 | Пользователь деактивирован |
| `VAL_INVALID_INPUT` | 400 / 422 | Валидация тела/параметров |
| `VAL_NOT_FOUND` | 404 | Сущность не найдена |
| `VAL_CONFLICT` | 409 | Конфликт состояния |
| `IDEMPOTENCY_CONFLICT` | 409 | `Idempotency-Key` повторён с другим телом |
| `JOB_IN_PROGRESS` | 409 | Звонок уже обрабатывается |
| `JOB_NOT_READY` | 400 | Экспорт/отчёт ещё не готов |
| `FEATURE_DISABLED` | 403 | Feature toggle выключен |
| `DB_ERROR` | 500 | Ошибка БД (текст скрыт) |
| `EXT_WEBITEL_UNAVAILABLE` | 502 | Webitel недоступен |
| `EXT_LLM_UNAVAILABLE` | 502 | LLM недоступен |
| `EXT_STT_UNAVAILABLE` | 503 | STT недоступен |
| `EXT_STORAGE_UNAVAILABLE` | 502 | MinIO недоступен |
| `INTERNAL` | 500 | Непредвиденная ошибка |

Клиент должен показывать `message` пользователю и передавать `trace_id` в поддержку.
Не логируйте и не отображайте сырые `detail` исключений.
