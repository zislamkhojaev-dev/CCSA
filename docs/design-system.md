# Дизайн-система UI

Flat / neutral developer-tool aesthetic (Cursor / VS Code / Linear).

## Файлы

| Файл | Назначение |
|------|------------|
| `frontend/src/design-system.css` | Токены, базовые компоненты, sidebar, кнопки, формы |
| `frontend/src/styles.css` | Страничные стили (звонки, дашборд, плейграунд, транскрипт) |

`styles.css` импортирует `design-system.css` — при редизайне правьте токены и базовые компоненты в design-system, page-specific — в styles.

## Тема по умолчанию

**Светлая** (`data-theme="light"`). Переключатель в сайдбаре сохраняет выбор в `localStorage` (`ccsa-theme`).

## Акцент

Нейтральный **charcoal** (не синий, не фиолетовый):

- Light: кнопки primary `#2d2f33` на белом
- Dark: primary `#e4e5e9` на тёмном фоне

## Шрифт

`system-ui` — без загрузки внешних шрифтов.

## Ключевые токены

```css
--bg, --surface, --surface2, --border
--text, --text-strong, --muted, --faint
--primary, --primary-hover, --on-primary
--state-hover, --state-selected, --focus-ring
--green, --yellow, --red (+ *-soft)
--shape-sm (6px), --shape-md (8px), --control-h (32px)
```

Legacy-алиасы `--md-*` сохранены для совместимости со старыми правилами в `styles.css`.

## Принципы

1. **Border-first** — карточки и панели с `border: 1px solid`, без теней.
2. **Компактность** — body 13px, контролы 32px.
3. **Скругления 6–10px** — не pill-кнопки.
4. **Тени** — только dropdown, modal, login-card.
