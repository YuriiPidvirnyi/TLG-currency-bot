# Dental Story Bot — context для Claude

> Цей файл — primer для будь-якої нової Claude-сесії в цьому репо. Прочитай його перед тим, як планувати або писати код.

## Продукт

Telegram-бот для централізованого збору заявок на витратні матеріали в стоматологічній клініці **Dental Story**:
- **3 кабінети** — окремі робочі зони, для яких треба замовляти матеріали.
- **Асистенти** додають позиції від імені свого кабінету та лікаря.
- **Адміністратор** раз на 1–2 тижні перевіряє накопичені заявки, фіналізує і закриває цикл — бот формує зведений документ замовлення.
- **Власниця клініки** отримує готовий звіт автоматично та може запитати поточний стан у будь-який час.

Раніше потреби збиралися усно/у різних месенджерах, що приводило до забутих позицій, дублів і ручної консолідації списків.

## Стек

- **Runtime:** Python 3.12, `aiogram 3.x`, FSM на `MemoryStorage`.
- **БД:** SQLite через `aiosqlite`, файл `/data/clinic.db` на Railway persistent volume.
- **Розклад:** `APScheduler` (`AsyncIO`) — нагадування адміну за cron-розкладом.
- **Звіти:**
  - `openpyxl` — XLSX (лист «Зведено» + по кабінетах + по постачальниках із префіксом `П-`).
  - `reportlab` + `LiberationSans` — PDF з кириличним шрифтом і логотипом.
  - Текстовий summary в Telegram (Markdown).
- **Деплой:** Railway, чинний `Dockerfile` + `railway.toml` з volume `/data`.
- **Ідентифікація:** Telegram `user_id` (не `chat_id`) — працює і в DM, і в групових чатах.

## Ролі

| Роль | Команди |
|---|---|
| `assistant` | `/add`, `/my`, `/del <id>`, `/cabinet` |
| `admin` | усе вище + `/open`, `/close`, `/preview`, `/pending`, `/approve <id>`, `/reject <id>`, `/allapprove`, `/catalog [add|del]`, `/users [add|del]`, `/cycle` |
| `owner` | `/report`, `/history`, `/get <cycle_id>` |

Перший admin сидиться при старті з env `ADMIN_CHAT_ID`. Решта через `/users add`. Доступ — whitelist у БД (middleware `AuthMiddleware`).

## Модель даних (SQLite)

```
users(id, tg_id UNIQUE, full_name, role, default_cabinet_id, created_at)
cabinets(id, name)                                    -- seed: Кабінет 1/2/3
catalog_items(id, name, unit, supplier?, default_qty, archived_at?)
order_cycles(id, status[open|closed], opened_at, opened_by, closed_at?, closed_by?)
order_requests(id, cycle_id, user_id, cabinet_id,
               catalog_item_id?, free_form_name?,
               qty, unit, comment?, doctor_name?,
               status[pending|approved|rejected],
               created_at, updated_at)
reports(id, cycle_id, generated_at, xlsx_path, pdf_path, summary_text)
audit_log(id, user_id, action, payload_json, ts)
```

**Інваріанти:**
- Один активний цикл за раз (`UNIQUE INDEX WHERE status='open'`).
- Каталог-позиції створюються `approved`; free-form → `pending`, на ревʼю в `/pending`.
- У звіті дублі по `(cycle, cabinet, catalog_item)` агрегуються по `qty`.

## Структура коду

```
bot.py                       entry point — wires DB, scheduler, routers
app/
  config.py                  env, шляхи, asset/migrations dir
  db.py                      aiosqlite + run-once migrations + seed
  models.py                  dataclass-сутності
  middlewares/auth.py        whitelist + role inject у handler data
  fsm/add_item.py            стани майстра /add
  handlers/
    start.py                 /start /help /whoami
    assistant.py             /add (FSM), /my, /del, /cabinet
    admin.py                 /open /close /preview /pending /approve
                              /reject /allapprove /catalog /users /cycle
    owner.py                 /report /history /get
  services/
    cycles.py                open/close, агрегати, останні цикли
    catalog.py               CRUD каталогу, кабінети
    requests.py              CRUD заявок, статуси, видалення
    reports.py               XLSX/PDF/text summary; брендинг #AECED3
    notifications.py         розсилка owner-ам, нагадування admin-ам
  scheduler.py               APScheduler: cron-нагадування
migrations/001_init.sql      seed cabinets 1/2/3
assets/brand/logo.png        Dental Story Blue PNG (XLSX header)
assets/brand/logo-bw.png     Dental Story Black PNG (PDF header)
docs/INITIAL_PLAN.md         оригінальний план дизайну
```

## Брендинг Dental Story

- Назва клініки: **Dental Story**. Default `CLINIC_NAME=Dental Story`.
- Фірмовий блакитний: `#AECED3` (заголовки таблиць, акценти).
- Темний текст у заголовках: `#1F2D3D`.
- Логотип:
  - `assets/brand/logo.png` — кольоровий, для XLSX summary sheet (топ-лів, ~110×88px).
  - `assets/brand/logo-bw.png` — монохром, для PDF (топ-лів, 28×22 mm).
- Constants: `BRAND_BLUE`, `BRAND_TEXT_DARK` у `app/services/reports.py`.

## Конфіг (Railway env)

```
BOT_TOKEN=...
ADMIN_CHAT_ID=...           # перший адмін (сидиться при старті, якщо не існує)
OWNER_CHAT_ID=...           # власниця (сидиться як owner)
CLINIC_NAME=Dental Story
DB_PATH=/data/clinic.db
REPORTS_DIR=/data/reports
REMINDER_CRON=0 16 * * 5    # Пт 16:00, нагадування адміну
TZ=Europe/Kyiv
```

Volume на Railway: mount `/data`, name `clinic-data`.

## Ключові потоки

**Assistant /add (FSM):** перевірка відкритого циклу → кабінет (default з users) → каталог inline-кнопки top-10 + пошук + «➕ Своя позиція» → к-сть+одиниця → лікар (опц) → коментар (опц) → confirm → запис.

**Admin /close:** preview к-сті approved/pending → якщо є pending → скерувати в /pending → інакше: `services.reports.generate_report()` (XLSX лист «Зведено» + по кабінетах + по постачальниках із префіксом `П-` + «П-Інше»; PDF з логотипом і кирилицею; Markdown summary) → файли в `/data/reports/cycle_<id>/` → auto-DM owner-ам → цикл `closed` → новий `open`.

**Owner:** `/report` (preview без зміни статусу), `/history` (топ-10 циклів), `/get <id>` (повторна відправка файлів).

**Розклад:** APScheduler cron `REMINDER_CRON` нагадує адмінам. Без авто-`/close` — закриття завжди ручне.

## Що вже зроблено

- Повний бекенд + FSM + усі ролі + звіти + брендинг.
- E2E smoke перевірено: міграції → каталог + free-form → approve → XLSX (7 листів) + PDF з логотипом і кирилицею + Markdown summary.

## Відкриті питання (передати наступному циклу)

- `doctor_name` як окрема колонка — лишити чи прибрати.
- Бренд/виробник у `name` чи окрема колонка `brand`.
- Множинна привʼязка assistant↔cabinet (зараз один `default_cabinet_id`).
- `/stats` (топ позицій, динаміка по циклах) — не реалізовано.
- Перший прогін на Railway з реальним volume.

## Передісторія

Починалось як перепрофілювання `tlg-currency-bot`. Після рев'ю переміщено в окреме репо `TLG-ds-order-bot`. Брендовий пакет `Dental_Story.rar` розпаковано, кольори/логотип витягнуто. Closed PR `tlg-currency-bot#22` — там оригінальна історія дизайнерських рішень.
