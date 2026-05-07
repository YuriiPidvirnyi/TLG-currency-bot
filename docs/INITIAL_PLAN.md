# Telegram-бот замовлення витратних матеріалів для стоматологічної клініки

## Контекст

Стоматологічна клініка з 3 кабінетами потребує централізованого процесу замовлення витратних матеріалів. Сьогодні асистенти повідомляють потреби різними каналами (усно, у месенджерах), що призводить до забутих позицій, дублів і ручної консолідації списків. Завдання — побудувати Telegram-бот, який:

- дозволяє асистентам оперативно реєструвати потреби від імені кабінету та лікаря;
- адміністратору — фіналізувати, правити й закривати цикл замовлення (раз на 1–2 тижні);
- власниці клініки — отримувати готовий документ автоматично та переглядати на вимогу;
- зберігає історію та дає аналітику витрат у часі/по кабінетах.

## Ролі та права

| Роль | Команди / можливості |
|---|---|
| `assistant` | `/add` додати позицію, `/my` переглянути/редагувати свої позиції в активному циклі, `/cabinet` змінити дефолтний кабінет |
| `admin` | усе вище + `/open`, `/close` (формує звіт), `/pending` (ревʼю free-form позицій), `/catalog`, `/users`, `/cycle` |
| `owner` | `/report` (поточний чорновий зведений звіт), `/history` (попередні цикли + файли), отримує автоматичну розсилку при `/close` |

Перший admin задається через `ADMIN_CHAT_ID` у env. Усі інші користувачі додаються admin-ом через `/users add <tg_id> <role> [cabinet]`. Доступ — суворо за whitelist у БД.

## Інфраструктура

- **Runtime:** Python 3.12, `aiogram 3.x`, FSM зі вбудованим `MemoryStorage` (для UX майстра додавання позиції).
- **БД:** SQLite через `aiosqlite`, файл `/data/clinic.db` на Railway persistent volume. Достатньо для ~10 користувачів і десятків тисяч позицій; уникає окремого Postgres-сервісу.
- **Розклад:** `APScheduler` (AsyncIO scheduler) для нагадувань адміну в обраний день тижня та опційного авто-закриття.
- **Звіти:**
  - `openpyxl` — XLSX (зведений лист + лист на кабінет + лист на постачальника);
  - `reportlab` з `LiberationSans` (вже у Docker через `fonts-liberation`) — PDF з кириличним шрифтом;
  - короткий текстовий summary в Telegram з підсумками по кабінетах.
- **Деплой:** Railway, чинний Dockerfile + `railway.toml`. Додати декларацію volume для `/data`.
- **Ідентифікація:** Telegram `user_id` (не `chat_id`) — щоб бот працював як в особистому, так і в груповому чаті.

## Модель даних (SQLite)

```
users(id, tg_id UNIQUE, full_name, role, default_cabinet_id, created_at)
cabinets(id, name)                                    -- seed: Кабінет 1/2/3
catalog_items(id, name, unit, supplier NULLABLE,
              default_qty, archived_at NULLABLE)
order_cycles(id, status, opened_at, opened_by,
             closed_at NULLABLE, closed_by NULLABLE)  -- status: open|closed
order_requests(id, cycle_id, user_id, cabinet_id,
               catalog_item_id NULLABLE,              -- NULL якщо free-form
               free_form_name NULLABLE,
               qty, unit, comment, doctor_name NULLABLE,
               status,                                -- pending|approved|rejected
               created_at, updated_at)
reports(id, cycle_id, generated_at, xlsx_path, pdf_path, summary_text)
audit_log(id, user_id, action, payload_json, ts)
```

Унікальність: один активний цикл за раз (`status='open'`). Free-form позиції створюються зі `status='pending'` і потрапляють у чергу `/pending` адміна; обрані з каталогу — одразу `approved`.

## Структура коду

```
bot.py                  -> точка входу, стартує app
app/
  config.py             -> env, шляхи
  db.py                 -> aiosqlite pool, міграції
  models.py             -> dataclass-и сутностей
  middlewares/auth.py   -> whitelist + role check
  handlers/
    start.py
    assistant.py        -> /add (FSM), /my, /cabinet
    admin.py            -> /open, /close, /pending, /catalog, /users, /cycle
    owner.py            -> /report, /history
  fsm/add_item.py       -> стани майстра додавання
  services/
    cycles.py           -> open/close, агрегація
    catalog.py
    reports.py          -> XLSX (openpyxl), PDF (reportlab), text summary
    notifications.py    -> розсилка owner-у/admin-у
  scheduler.py          -> APScheduler jobs (нагадування)
migrations/
  001_init.sql
```

## Ключові флоу

**Додавання позиції (assistant `/add`):**
1. Якщо немає відкритого циклу — повідомити «цикл закритий, зверніться до адміна».
2. Кабінет: підставляється `default_cabinet_id`, кнопка «Змінити».
3. Каталог: inline-пошук по назві + кнопка «➕ Своя позиція».
4. Кількість + одиниця (підставляється з каталогу).
5. Опційно: лікар (текст), коментар (терміновість/бренд).
6. Підтвердження → запис. Дублі того самого `(cycle, cabinet, catalog_item)` агрегуються по `qty`.

**Закриття циклу (admin `/close`):**
1. Бот показує preview: к-сть позицій, к-сть pending free-form. Якщо є pending — підказати `/pending`.
2. Підтвердження → `services.reports.generate(cycle_id)`:
   - XLSX: лист «Зведено», листи по кожному кабінету, листи по постачальнику + лист «Інше».
   - PDF: титул (назва клініки, період, дата), таблиці аналогічно.
   - Текстовий summary в чат.
3. Файли зберігаються в `/data/reports/<cycle_id>/`, шляхи — у `reports`.
4. Auto-DM owner-у з обома файлами + summary. Цикл переходить у `closed`. Auto-create наступний `open` цикл.

**Owner on-demand:**
- `/report` — генерує preview поточного відкритого циклу (без переведення статусу).
- `/history` — список останніх 10 циклів, по тапу — повторна відправка файлів.

**Розклад:**
- Cron-нагадування адміну (наприклад, пʼятниця 16:00, конфігуровано через env `REMINDER_CRON`): «Сьогодні плановий день закриття циклу».
- Без авто-`/close` — фінальне закриття завжди ручне.

## Аналітика (планована v2)

- `/stats` (admin/owner): сумарна кількість і витрати позиції X за останні N циклів, топ-10 позицій по кабінету, динаміка кількості циклів.
- Для PDF-аналітики — переюзати `Pillow`-рендер для графіка.

## Перевірка (end-to-end)

1. `docker build` локально → `docker run` з `BOT_TOKEN` тестового бота.
2. Перший запуск з `ADMIN_CHAT_ID` — admin отримує `/start` з повним меню. Інший Telegram акаунт без whitelist — отримує «доступ заборонено».
3. Admin: `/users add <tg_id_2> assistant 1`, `/catalog add "Рукавички латексні M" уп 5 "Дентал-Сервіс"`, `/open`.
4. Assistant: `/add` → обирає каталог-позицію → 10 уп → коментар «терміново». Перевірити `/my`. Додати free-form → бачимо що pending.
5. Admin: `/pending` → approve free-form. `/close` → отримати XLSX + PDF + текст. Owner-акаунт отримує DM з тим самим набором.
6. Owner: `/history` повертає попередній цикл, `/report` працює на новому відкритому циклі.
7. Перезапуск контейнера: дані лишаються (volume), активний цикл — той самий.

## Відкриті точки рішення

- **Лікар у позиції** — окреме поле чи частина коментаря? Поки `doctor_name` як окрема колонка.
- **Бренд/виробник у каталозі** — додати поле `brand` чи в `name`? Поки в `name`.
- **Множинна привʼязка асистента до кабінетів** — поки один `default_cabinet_id` + ручний вибір при `/add`.
- **Розмір/глибина історії** — поки 10 останніх циклів у `/history`.
