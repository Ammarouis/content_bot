# ITGenix Academy – Content Management Bot: System Design

## 1. Architecture

```
┌───────────────────────────── Telegram ─────────────────────────────┐
│ private chats (Admin / Uploader / Student)   4 channels (temp/approved PDF/TEX) │
└──────────────┬─────────────────────────────────────────▲───────────┘
               │ updates (long polling)                  │ Bot API calls
┌──────────────▼──────────────────────┐   ┌──────────────┴───────────────┐
│ handlers/  (aiogram routers)        │   │ services/telegram_gateway.py │
│  common · student · review ·        │   │  retry on RetryAfter/network,│
│  admin_users · admin_academic ·     │   │  error classification        │
│  admin_content · admin_settings     │   └──────────────▲───────────────┘
│  + middlewares/auth (RBAC, private) │                  │
│  + permissions.HasRole router filter│                  │
└──────────────┬──────────────────────┘                  │
               │ calls                                   │
┌──────────────▼─────────────────────────────────────────┴───────────┐
│ services/  business logic (no Telegram UI code, no Arabic text)    │
│  users · academic · content (submit/resubmit/approve/reject/delete)│
│  settings · cleanup (DB-backed deletion queue + recovery worker)   │
└──────────────┬─────────────────────────────────────────────────────┘
               │ SQL inside short transactions (never across API calls)
┌──────────────▼──────────────────────┐
│ db/  database.py (aiosqlite, WAL,   │
│      BEGIN IMMEDIATE tx, FK ON)     │
│      repositories.py · schema.sql   │
└─────────────────────────────────────┘
config.py (env vars) · logging_setup.py (JSON/text structured logs) · texts.py (all Arabic strings)
```

Layer rules
* **handlers** parse input, call services, render with `texts`/`keyboards`. No SQL.
* **services** enforce business rules *and* re-check permissions against the DB (defence in depth).
* **repositories** are the only place with SQL.
* **texts.py** is the only place with user-facing strings (Arabic only).

## 2. Database schema (SQLite, relational, FK enforced)

| Table | Purpose | Key constraints |
|---|---|---|
| `academic_years` | Years 1–5 (seeded) | `requires_specialization` = 1 for years 4,5 |
| `specializations` | Per-year specializations | `UNIQUE(year_id,name)`; trigger: only for years requiring it |
| `subjects` | Subjects | `code UNIQUE`, `CHECK` code = `[A-Z][A-Z0-9]{1,19}`; triggers enforce spec required / forbidden / same year; v2: `semester IN (1,2) NOT NULL`, `semester_confirmed` |
| `users` | Registered users | PK `telegram_id`; `role IN (admin,uploader,student)` |
| `student_subjects` | Subjects assigned to students | PK(student, subject); cascades |
| `contents` | One record per lecture/session | `UNIQUE(subject_id, content_type, number)`; `status` CHECK; rejected ⇒ reason NOT NULL |
| `content_files` | Current PDF/TEX location of a content | PK(content_id, kind); `UNIQUE(chat_id,message_id)`; cascade; v2: `protect_requested`, `protected` (Telegram's `has_protected_content`, NULL = unknown) |
| `preview_messages` | Review/preview copies sent to private chats | cascade; auto-expire after TTL |
| `deletion_jobs` | One per admin deletion request | status `in_progress/completed/needs_attention` |
| `cleanup_queue` | Every Telegram message that must be deleted | `UNIQUE(chat_id,message_id)`; status `held/pending/done/failed`; attempts, backoff, last_error |
| `settings` | key/value: `support_username` (protection is **not** a setting since v3) | |

Indexes: `contents(status, submitted_at)`, `contents(student_id, submitted_at)`, `contents(subject_id, status)`,
`subjects(year_id, specialization_id)`, `users(role)`, `student_subjects(subject_id)`,
`cleanup_queue(status, next_attempt_at)`, `cleanup_queue(job_id, status)`, `cleanup_queue(content_ref, status)`, `preview_messages(created_at)`.

## 3. Content state machine

```
          submit (reserve number)           all files posted to temp channels
  ∅ ───────────────────────────▶ uploading ───────────────────────────▶ pending ◀─────────┐
                                    │ failure / crash recovery                │  │          │
                                    ▼                                         │  │ reject   │ resubmit OK
                              (row deleted, number freed,                     │  ▼ (reason)│
                               sent files queued for deletion)                │ rejected ──┼──▶ resubmitting
                                                                              │            │       │ failure
                                                     approve (claim)          │            └───────┘ → rejected
                                                         ▼                    │
                                                    approving ──failure──────▶┘ (approved copies queued for deletion)
                                                         │ copies posted to approved channels
                                                         ▼
                                                      approved   (temp messages queued for deletion)
 any of pending/approved/rejected ── admin delete (confirmed) ──▶ row deleted, every message queued in a deletion job
```

* Transitional states (`uploading`, `approving`, `resubmitting`) are **claims**: obtained with a conditional
  `UPDATE … WHERE status = <expected>` inside `BEGIN IMMEDIATE` ⇒ concurrent approvals/rejections/deletions
  cannot both succeed.
* **Held messages**: every message the bot posts to a channel during an operation is immediately recorded in
  `cleanup_queue` with status `held`. On commit the hold is released (reference moved to `content_files`);
  on failure the hold becomes `pending` (deleted by the worker). This closes the gap between a Telegram call and the DB write.
* **Crash recovery**: on startup all transitional records are rolled back (and periodically, those older than
  `STALE_OPERATION_MINUTES`).

## 4. Workflows

**Student submission:** subject (assigned only) → type → number (duplicate check) → PDF or *skip with reason* →
mandatory `.tex` → summary → confirm. Files stay as Telegram `file_id`s in FSM until confirmation, so an
abandoned wizard leaves nothing behind.

**Rejection & resubmission:** reject requires a reason. Student opens *المحاضرات المرفوضة* → *إرفاق ملفات جديدة* →
PDF (mandatory now) → TEX → confirm. The same record is updated, `pdf_skip_reason` cleared, status → pending,
old temp messages queued for deletion, the last rejection reason kept until the next decision. No history kept.

**Approval:** claim → copy PDF/TEX to approved channels (held) → commit: status approved, store new message ids,
queue temp messages + review copies for deletion.

**Deletion:** confirm screen with exact details → single transaction: create job, queue all file messages,
review copies and any outstanding queue entries of that record, delete row (number freed). The job is processed
immediately; the admin gets "fully deleted" only if every message is gone; otherwise a partial report and a
later notification when the worker finishes (or needs attention after max attempts).

## 5. Role permissions

| Capability | Admin | Uploader | Student |
|---|:-:|:-:|:-:|
| /start, support info | ✔ | ✔ | ✔ |
| My subjects, last 5, submit, rejected list, resubmit (own records only, assigned subjects only) | – | – | ✔ |
| Review queue, view files, approve, reject, approved content browser | ✔ | ✔ | – |
| User management (add/role/remove/assign subjects) | ✔ | – | – |
| Years/specializations/subjects | ✔ | – | – |
| Content search, delete, cleanup queue | ✔ | – | – |
| Support settings, channel check | ✔ | – | – |

Enforcement: (1) auth middleware rejects unregistered users and non-private chats; (2) every router carries a
`HasRole` filter (callback data forged for another role never reaches the handler); (3) services re-load the
user from the DB and re-check role/ownership before every mutation. Bootstrap admins (`ADMIN_IDS`) cannot be
removed or demoted from inside the bot, and an admin cannot remove themselves.

## 6. Security risks & failure scenarios

| Risk / failure | Mitigation |
|---|---|
| Unregistered access, forged callback data | Middleware + router filters + service re-checks |
| Group/channel abuse | Only private chats processed |
| Wrong file types / oversize | Extension + MIME checks, size limits from env |
| Duplicate numbers (incl. race) | UNIQUE constraint is authoritative; early friendly check |
| Concurrent approve/reject/delete | Conditional UPDATE claims inside IMMEDIATE transactions |
| Telegram 429 / network errors | Gateway retries with `retry_after` / backoff |
| Crash between API call and DB write | Held queue entries + startup recovery |
| Partial approval (PDF copied, TEX failed) | Roll back to pending, queue copies for deletion |
| Deletion failure (permissions, outages) | Persistent queue, exponential backoff, `failed` after max attempts, admin retry, never "done" until all gone |
| Private-chat delete limit (48h) | Review copies expire after `PREVIEW_TTL_HOURS` (default 24) |
| Screenshot prevention | Only `protect_content` exists in Bot API (blocks forward + save together; screenshots blocked only on some clients). Channel "Restrict saving content" must be set by the owner; bot reports its state. Clearly stated in UI. |
| Secrets | Token and IDs only via environment variables / `.env`, never logged |

## 7. Implementation plan
1. Config, logging, schema, DB layer, repositories.
2. Telegram gateway, services (users, academic, settings, content, cleanup).
3. Middlewares, permissions, callback factories, keyboards, texts.
4. Handlers per role.
5. Tests: repository/service unit tests and end-to-end handler tests with a mocked Bot API session.

## 8. v2 additions
* **Schema versioning.** `PRAGMA user_version` (now 3). `database.py` runs ordered migrations (`MIGRATIONS`)
  before `schema.sql`. Each migration runs in its own transaction, after a `VACUUM INTO` backup.
* **Protection model (v3, permanent).** `bot/policy.py`: `protect_for_role(role)` is true only for students, and
  `protect_for_stage(stage)` is true only for approved channels. `StudentProtectionMiddleware` (a session request
  middleware registered in `build_services`) sets `protect_content` on every outgoing method that has the field,
  based on the recipient. That means approved channels and students are protected; temp channels, admins,
  uploaders and strangers are not. A role lookup that fails is treated as protected. Roles are read on a separate
  read-only SQLite connection, so a Telegram call inside a transaction can't deadlock on the write lock. A file
  is *outdated* when `protect_requested` differs from the rule for its stage. `ProtectionService.sync_tick` runs
  on every worker tick and re-posts outdated files. Each re-post is first **held** in `cleanup_queue` and swapped
  into `content_files` only if the row and status are unchanged; otherwise the hold is activated and the new post
  is deleted. The old post is always queued for deletion. Migration v3 removes every protection setting.
* **Approved hierarchy** (review router, `Rv`): `ay` years → `ayy` specs (years 4/5) → `asm` semester (x=year,
  y=spec|0, p=semester) → `asb` subject → `atl` type list → `av` item card. Approved counts are shown at every level
  and computed from one grouped query.
* **Number picker** (`St`): `nbp` page, `nb` available, `nbx` occupied. Every button carries the wizard nonce `n`
  stored in FSM; a mismatch means a stale keyboard. Statuses are read live on every render and re-checked when a
  number is pressed. `UNIQUE(subject_id, content_type, number)` stays the final guard for concurrent submissions.
  Pending covers all transitional states.
