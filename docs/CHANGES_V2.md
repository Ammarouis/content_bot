# v2 Enhancement – Inspection Findings & Modification Plan

## Findings (v1 codebase)
| Area | v1 implementation | Gap vs. new requirements |
|---|---|---|
| Protection | Two keys `protect_forwarding` / `protect_saving`, OR-ed into one `protect_content` flag applied to every message (admins included) | No audience, admins restricted, existing posts untouched, nothing verified |
| File delivery | `send_document` for temp posts, `copyMessage` for approval/previews | `copyMessage` returns only a message id → protection cannot be verified |
| Approved browsing | Flat "subjects with approved content" list (admin + uploader, two copies of the same screens) | No year/spec/semester/type hierarchy; duplicated code |
| Subjects | year + specialization, no semester | Semester missing |
| Number entry | Free-text number | Needs status-coloured inline picker with paging |
| Rejected flow, deletion, cleanup queue | Implemented & tested | Keep; add regression tests (repeat rejection → approval) |
| Schema versioning | `PRAGMA user_version = 1`, idempotent `schema.sql` | Needs ordered migrations |

## Plan (minimal, in place)
1. **DB migration v1 → v2** (`database.py` migration runner, transactional):
   * `subjects.semester` (1|2, NOT NULL, CHECK) + `semester_confirmed`; existing subjects get semester 1 and are flagged for admin review (nothing deleted).
   * `content_files.protect_requested` + `protected` (actual flag returned by Telegram).
   * Old protection keys → `protection_enabled` + `protection_audience` (`all`).
2. **Unified protection** (`services/settings.py`, new `services/protection.py`): one switch + audience; per-role rule, admin never protected; temp channels = uploader-facing, approved channels = student-facing; deliveries use the recipient's role. All posts via `sendDocument` (returns `has_protected_content` → verified & stored). Existing posts re-published silently in the background when the setting changes (DB-tracked, hold-protected, retried by the worker).
3. **Single approved-content hierarchy** (review router, shared by admin + uploader): year → specialization (4/5) → semester → subject → type → items; admin gets delete actions on the same item card. Old flat screens removed.
4. **Semester in subject management**: year → specialization → semester → subjects (+ add); edit semester; review list for migrated subjects.
5. **Number picker**: 20 per page, «المزيد», status icons 🟢/🟡/🔴, occupied numbers answer with an alert, server-side re-check, wizard nonce against stale keyboards; UNIQUE constraint stays authoritative.
6. Texts / keyboards updated; tests extended for all 16 QA items + v1→v2 migration.

## Implemented (status: done, 47 tests passing)
| File | Change |
|---|---|
| `bot/db/schema.sql`, `bot/db/database.py` | v2 columns + `idx_subjects_hierarchy`; ordered migration runner with pre-migration backup |
| `bot/db/repositories.py`, `bot/models.py` | semester fields, protection columns, `number_statuses`, `approved_counts`, protection sync queries, `Sent`, `number_category` |
| `bot/services/settings.py` | `Protection(enabled, audience)` with `for_role` / `for_stage`; sync-pending flag |
| `bot/services/protection.py` (new) | verified status, background re-publication with hold-protected swap |
| `bot/services/content.py` | all deliveries via `sendDocument` → verified flag; role-based previews; hierarchy counts |
| `bot/services/academic.py`, `validators.py` | semester on create/edit, unconfirmed list |
| `bot/services/telegram_gateway.py`, `cleanup.py`, `container.py` | `Sent` result, silent posts, periodic hook, nullable hold |
| `bot/handlers/review.py` | single approved hierarchy shared by admin + uploader; shared item card |
| `bot/handlers/student.py` | number picker (20/page, «المزيد»/«السابق», 🟢🟡🔴, refresh, nonce, server re-check) |
| `bot/handlers/admin_academic.py` | year → spec → semester → subjects; semester edit/confirm; unconfirmed list |
| `bot/handlers/admin_settings.py` | protection screen (switch, audience, verification counters, sync state); channel policy line |
| `bot/handlers/admin_content.py`, `common.py`, `admin_users.py` | flat approved screens removed; menus point to the hierarchy; semester shown in assignments |
| `bot/texts.py`, `bot/callbacks.py` | v2 Arabic strings; `Rv.y`, `St.n` |
| `tests/test_v2.py` (new), `tests/fixtures/schema_v1.sql` (new), `tests/fake_telegram.py`, `tests/conftest.py`, existing tests | v2 coverage, realistic `has_protected_content`, picker helpers |

## v3: permanent student protection (status: done, 70 tests passing)
| File | Change |
|---|---|
| `bot/policy.py` (new) | Hardcoded rule (`protect_for_role`, `protect_for_stage`) and `StudentProtectionMiddleware`, which applies to every outgoing Bot API request |
| `bot/db/database.py` | Schema v3 migration that deletes all protection settings; `role_of()` on a lock-free read-only connection |
| `bot/services/settings.py` | Protection settings, audience, toggles and sync flag removed; support username only |
| `bot/services/protection.py` | Fixed rule, runs on every worker tick, no admin trigger; `stats()` for read-only reporting |
| `bot/services/content.py`, `container.py` | Use the fixed rule; middleware registered; no settings dependency |
| `bot/handlers/admin_settings.py`, `bot/texts.py` | Protection screen, switch and audience buttons removed; channel check shows a read-only note |
| `tests/test_student_protection.py` (new), `tests/fake_telegram.py`, `test_v2.py`, `test_flows.py` | Permanent-rule coverage; fake API reports `has_protected_content` for text messages too |
