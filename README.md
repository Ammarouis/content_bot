# ITGenix Academy – Telegram Content Management Bot

A private bot, with an Arabic-only interface, that manages academic content (lectures and sessions) from student
submission through review and approval to archiving in Telegram channels.
Built with Python 3.11+, **aiogram 3** and **SQLite** (aiosqlite). Runtime dependencies: these two only.

Design document (architecture, schema, state machine, permissions, risks): [`docs/DESIGN.md`](docs/DESIGN.md)

## Project layout
```
bot/
  __main__.py          entry point (python -m bot)
  app.py               bot/dispatcher assembly, global error handler, background worker
  config.py            environment configuration (+ minimal .env loader)
  logging_setup.py     structured JSON / text logs
  models.py            domain models & enums
  texts.py             every Arabic string
  callbacks.py         callback-data factories (one prefix per permission area)
  permissions.py       HasRole router filter + service-level require_role
  middlewares/auth.py  private-chat + registered-user gate
  keyboards/           inline keyboard helpers (pagination, support button)
  db/                  schema.sql, database.py (transactions), repositories.py (all SQL)
  services/            users, academic, settings, content, cleanup, telegram_gateway, notifier, container
  handlers/            common, student, review, admin_users, admin_academic, admin_content, admin_settings
  notifications.py     Arabic Telegram notifications (Notifier implementation)
tests/                 end-to-end handler tests with a fake Bot API + reliability tests
```

## Setup
1. Create the bot with **@BotFather** and copy the token.
2. Create **four private channels**: temporary PDF, temporary TEX, approved PDF, approved TEX.
   Add the bot to each as an **administrator** with *Post messages* and *Delete messages*.
   Student protection is built into the bot (see *Content protection* below). Leave the channel option
   **Restrict saving content** off on the temporary channels, because it would restrict uploaders there. The bot
   cannot change this option; it only reports it under *الإعدادات ← فحص القنوات*.
3. Get the channel IDs (they look like `-100…`). One way: forward a channel post to @userinfobot.
4. Configure:
   ```bash
   cp .env.example .env    # then edit the values
   ```
   `ADMIN_IDS` holds the bootstrap admins. They are always admins and cannot be removed or demoted from inside the bot.
5. Run:
   ```bash
   python -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   python -m bot
   ```
   With Docker: `docker build -t itgenix-bot . && docker run -d --env-file .env -v itgenix-data:/app/data itgenix-bot`

A new user sends `/start`. The bot replies with their Telegram ID, and an admin registers them from
*إدارة المستخدمين ← إضافة مستخدم*. Students then need subjects assigned (*المواد المسندة*).

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest -q
```
The suite drives real updates through the dispatcher, middlewares, routers, services and a real SQLite database.
A fake Bot API stands in for Telegram and simulates the channel messages. Covered: RBAC (including forged
callbacks), the full lifecycle (submit → duplicate check → preview → reject → resubmit → approve → search →
confirmed delete → number reuse), skipping the PDF with a reason, failed uploads and approvals rolling back,
concurrent approvals and duplicate submissions, partial deletion failures with retry and admin notification, crash
recovery, preview expiry, and academic constraints.
`tests/test_student_protection.py` covers the permanent student rule on real outgoing Bot API requests:
every send/copy/forward method for every recipient type, all student screens and notifications, channels and
reviewer previews, role changes, fail-closed lookups, attempts to disable it through the dashboard or the
database, re-publishing of existing posts (with retry and races against deletion/resubmission), and the v3
migration. `tests/test_v2.py` covers subject creation with semester and the specialization rule, the approved hierarchy and back navigation, picker paging,
status colours, occupied/forged/stale numbers, concurrent submissions, status refresh after every transition,
repeated rejection → approval, full deletion with retry, and the v1 → v2 migration on a real v1 database file.

## Upgrading from v1
Stop the bot, update the code and start it again. Nothing else is required:
* On startup, a v1 database (`PRAGMA user_version = 1`) is first copied to `data/itgenix.db.v1.bak` with
  `VACUUM INTO`. It is then migrated in one transaction (rolled back completely on any error).
* Existing subjects keep all data and are placed in **الفصل الأول** with a "needs confirmation" flag. The academic
  menu shows «⚠️ مواد بحاجة لتأكيد الفصل (n)». Open each subject and press «تأكيد الفصل الحالي» or «تغيير الفصل».
* All protection settings (`protect_forwarding`, `protect_saving`, `protection_enabled`, `protection_audience`,
  `protection_sync_pending`) are deleted (schema v3). Protection is now a fixed rule in the code. On its first
  cycle, the background worker re-posts any existing file that doesn't match the rule.
* No new environment variables were added.

## Operational notes
* **Single instance.** Run one bot process per database. Transactions are serialized inside the process, and
  `BEGIN IMMEDIATE` + WAL protect the file.
* **FSM state is in memory.** A restart resets any half-finished wizard. No files are posted before the final
  confirmation, so nothing is orphaned.
* **Cleanup worker.** Every `CLEANUP_INTERVAL_SECONDS` it: rolls back stuck operations, expires review copies
  (`PREVIEW_TTL_HOURS`, kept under Telegram's 48-hour private-chat deletion limit), retries due deletions with
  exponential backoff, and notifies admins when a deletion job finishes or needs attention.
* **Content protection: permanent for students.** This is a fixed rule in `bot/policy.py`, not a setting. It
  cannot be changed from the dashboard, the database or the UI.
  * Everything the bot sends to a **student** (messages, PDF/TEX/other documents, copies, forwards, media) and
    every post in the **approved channels** has Telegram's `protect_content` flag. **Admins and uploaders**, and
    the temporary review channels, always get unrestricted messages.
  * Enforcement: services pass the flag explicitly, and `StudentProtectionMiddleware` checks **every outgoing
    Bot API request**. It sets `protect_content` based on the recipient's current role, read from a separate
    read-only database connection. Future code paths are covered automatically. If the role can't be read, the
    message is protected.
  * Every file post uses `sendDocument`. The `has_protected_content` value Telegram returns is stored, and the
    channel check reports any file whose protection Telegram did not confirm.
  * Telegram cannot change protection on an existing message. Files posted before the rule (or under the old v2
    settings) are re-posted silently by the background worker and the old posts are deleted, so they move to the
    bottom of the channel. Failures are retried every cycle.
  * Telegram's limits: `protect_content` blocks forwarding and saving, and the official mobile apps also block
    screenshots and screen recording. Telegram Desktop/Web do not reliably block screenshots, and nothing stops
    someone photographing the screen.
  * Approved channels are protected for everyone who opens them, including admins and uploaders who are members,
    because Telegram applies the flag per message, not per viewer. Admins and uploaders always get unrestricted
    copies inside the bot through «عرض الملفات».
* **Backups.** Back up `data/itgenix.db`. Use `sqlite3 data/itgenix.db ".backup backup.db"` while the bot is running.
