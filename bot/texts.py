"""Every user-facing string (Arabic only). Dynamic values are HTML-escaped here."""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.models import AppUser, Content, Subject

_TZ = timezone.utc


def set_timezone(name: str) -> None:
    global _TZ
    try:
        _TZ = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        _TZ = timezone.utc


def fmt_time(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(_TZ)
    except ValueError:
        return ts
    return dt.strftime("%Y/%m/%d %H:%M")


def e(value) -> str:
    return escape(str(value)) if value is not None else "—"


ROLE_NAMES = {"admin": "مدير", "uploader": "مسؤول رفع", "student": "طالب"}
ROLE_NAMES_PLURAL = {"admin": "المدراء", "uploader": "مسؤولو الرفع", "student": "الطلاب"}
TYPE_NAMES = {"lecture": "محاضرة", "session": "جلسة"}
STATUS_NAMES = {
    "pending": "⏳ قيد المراجعة", "approved": "✅ معتمد", "rejected": "❌ مرفوض",
    "uploading": "🔄 قيد الرفع", "approving": "🔄 قيد الاعتماد", "resubmitting": "🔄 قيد إعادة الإرسال",
}
STATUS_ICON = {"pending": "⏳", "approved": "✅", "rejected": "❌", "uploading": "🔄", "approving": "🔄",
               "resubmitting": "🔄"}
SEMESTER_NAMES = {1: "الفصل الأول", 2: "الفصل الثاني"}
TYPE_PLURAL = {"lecture": "المحاضرات", "session": "الجلسات"}
# number picker: colour per occupation category (available numbers stay neutral)
NUMBER_ICON = {"approved": "🟢", "pending": "🟡", "rejected": "🔴", "available": ""}
NUMBER_STATE = {"approved": "معتمد", "pending": "قيد المراجعة", "rejected": "مرفوض"}
NUMBER_LEGEND = "🟢 معتمد   🟡 قيد المراجعة   🔴 مرفوض   • الرقم دون رمز: متاح"

# ───────────── buttons ─────────────
BTN_HOME = "🏠 القائمة الرئيسية"
BTN_BACK = "↩️ رجوع"
BTN_CANCEL = "✖️ إلغاء"
BTN_CONFIRM = "✅ تأكيد"
BTN_PREV = "◀️ السابق"
BTN_NEXT = "التالي ▶️"
BTN_SUPPORT = "🆘 الدعم الفني"
BTN_CONTACT_SUPPORT = "💬 مراسلة الدعم"

BTN_MY_SUBJECTS = "📚 موادي"
BTN_RECENT = "🕘 آخر 5 محاضرات وجلسات تم رفعها"
BTN_UPLOAD = "📤 رفع محتوى جديد"
BTN_REJECTED = "❌ المحاضرات المرفوضة"
BTN_SKIP_PDF = "⏭️ تخطي ملف PDF"
BTN_SUBMIT = "📨 إرسال للمراجعة"
BTN_ATTACH_NEW = "📎 إرفاق ملفات جديدة"

BTN_PENDING = "📝 المحاضرات التي تتطلب مراجعة"
BTN_APPROVED = "✅ المحاضرات والجلسات المعتمدة"
BTN_VIEW_FILES = "📄 عرض الملفات"
BTN_APPROVE = "✅ اعتماد"
BTN_REJECT = "❌ رفض"
BTN_CONFIRM_APPROVE = "✅ تأكيد الاعتماد"

BTN_USERS = "👥 إدارة المستخدمين"
BTN_ACADEMIC = "🎓 الإدارة الأكاديمية"
BTN_CONTENT = "🗂️ إدارة المحتوى"
BTN_REVIEW = "📝 مراجعة المحتوى"
BTN_SETTINGS = "⚙️ الإعدادات"

BTN_ADD_USER = "➕ إضافة مستخدم"
BTN_LIST_USERS = "📋 عرض المستخدمين"
BTN_ALL = "الكل"
BTN_CHANGE_ROLE = "🔁 تغيير الدور"
BTN_RENAME = "✏️ تعديل الاسم"
BTN_ASSIGN_SUBJECTS = "📚 المواد المسندة"
BTN_REMOVE_USER = "🗑️ حذف المستخدم"
BTN_CONFIRM_REMOVE = "🗑️ تأكيد الحذف"

BTN_YEARS = "📅 السنوات والاختصاصات"
BTN_SUBJECTS = "📖 المواد"
BTN_ADD_SPEC = "➕ إضافة اختصاص"
BTN_DELETE_SPEC = "🗑️ حذف الاختصاص"
BTN_ADD_SUBJECT = "➕ إضافة مادة"
BTN_EDIT_NAME = "✏️ تعديل الاسم"
BTN_EDIT_CODE = "🔤 تعديل الرمز"
BTN_DELETE_SUBJECT = "🗑️ حذف المادة"

BTN_APPROVED_CONTENT = "✅ المحاضرات والجلسات المعتمدة"
BTN_SEARCH = "🔍 البحث عن محتوى"
BTN_CLEANUP = "🧹 عمليات الحذف والتنظيف"
BTN_DELETE_CONTENT = "🗑️ حذف المحتوى"
BTN_CONFIRM_DELETE = "⚠️ تأكيد الحذف النهائي"
BTN_SHOW_ALL = "📋 عرض الكل"
BTN_RETRY_FAILED = "🔁 إعادة محاولة العمليات المتعثرة"
BTN_RUN_CLEANUP = "▶️ تشغيل التنظيف الآن"
BTN_REFRESH = "🔄 تحديث"

BTN_MORE = "المزيد ⏬"
BTN_LESS = "⏫ السابق"
BTN_EDIT_SEMESTER = "🗓️ تغيير الفصل"
BTN_CONFIRM_SEMESTER = "✅ تأكيد الفصل الحالي"
BTN_UNCONFIRMED = "⚠️ مواد بحاجة لتأكيد الفصل ({n})"
BTN_SUPPORT_SETTINGS = "🆘 إعدادات الدعم الفني"
BTN_EDIT_SUPPORT = "✏️ تعديل معرّف الدعم"
BTN_CHECK_CHANNELS = "🔎 فحص القنوات"


def on_off(flag: bool) -> str:
    return "مفعّل ✅" if flag else "معطّل ❌"


# ───────────── generic ─────────────
UNAUTHORIZED = ("⛔️ <b>عذراً، لا تملك صلاحية استخدام هذا البوت.</b>\n\n"
                "هذا البوت خاص بأكاديمية ITGenix، ولا يمكن استخدامه إلا من قِبل المستخدمين المسجلين من الإدارة.\n"
                "إذا كنت تعتقد أن هذا خطأ، يرجى التواصل مع إدارة الأكاديمية وتزويدها بمعرّفك: <code>{tid}</code>")
UNAUTHORIZED_ALERT = "⛔️ لا تملك صلاحية تنفيذ هذا الإجراء."
STALE_BUTTON = "⚠️ هذا الزر لم يعد صالحاً أو لا تملك صلاحية استخدامه."
USE_BUTTONS = "ℹ️ يرجى استخدام الأزرار للتنقل. أرسل /start لعرض القائمة الرئيسية."
CANCELLED = "تم الإلغاء."
UNEXPECTED_ERROR = "⚠️ حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى لاحقاً."
EMPTY_LIST = "لا توجد عناصر لعرضها."
PAGE = "صفحة {page} من {pages}"

WELCOME = {
    "admin": "👋 أهلاً {name}\n<b>لوحة تحكم المدير</b> — أكاديمية ITGenix\n\nاختر القسم المطلوب:",
    "uploader": "👋 أهلاً {name}\n<b>واجهة مسؤول الرفع</b> — أكاديمية ITGenix\n\nاختر القسم المطلوب:",
    "student": "👋 أهلاً {name}\n<b>واجهة الطالب</b> — أكاديمية ITGenix\n\nاختر القسم المطلوب:",
}

SUPPORT_INFO = "🆘 <b>الدعم الفني</b>\n\nللتواصل مع الدعم الفني يرجى مراسلة: @{username}"
SUPPORT_NOT_SET = "🆘 <b>الدعم الفني</b>\n\nلم يتم ضبط معرّف الدعم الفني بعد. يرجى التواصل مع إدارة الأكاديمية."

# ───────────── errors ─────────────
ERRORS = {
    "forbidden": "⛔️ لا تملك صلاحية تنفيذ هذا الإجراء.",
    "invalid_telegram_id": "⚠️ معرّف Telegram غير صالح. يجب أن يتكون من أرقام فقط (5 إلى 15 رقماً).",
    "invalid_name": "⚠️ الاسم غير صالح. يجب أن يتراوح طوله بين {min} و{max} حرفاً.",
    "invalid_role": "⚠️ الدور المحدد غير صالح.",
    "user_exists": "⚠️ هذا المستخدم مسجّل مسبقاً.",
    "user_not_found": "⚠️ المستخدم غير موجود.",
    "protected_admin": "⛔️ لا يمكن تعديل أو حذف مدير النظام الأساسي المحدد في إعدادات الخادم.",
    "cannot_modify_self": "⛔️ لا يمكنك تعديل دورك أو حذف حسابك بنفسك.",
    "user_delete_blocked": "⚠️ تعذّر حذف المستخدم بسبب ارتباطه ببيانات أخرى.",
    "not_a_student": "⚠️ يمكن إسناد المواد للطلاب فقط.",
    "year_not_found": "⚠️ السنة الدراسية غير موجودة.",
    "year_has_no_specializations": "⚠️ هذه السنة الدراسية لا تتضمن اختصاصات.",
    "specialization_not_found": "⚠️ الاختصاص غير موجود.",
    "specialization_exists": "⚠️ يوجد اختصاص بالاسم نفسه في هذه السنة.",
    "specialization_has_subjects": "⚠️ لا يمكن حذف الاختصاص لوجود مواد مرتبطة به. احذف المواد أولاً.",
    "specialization_required": "⚠️ يجب تحديد الاختصاص لمواد السنتين الرابعة والخامسة.",
    "specialization_not_allowed": "⚠️ لا يمكن تحديد اختصاص لمواد السنوات الأولى والثانية والثالثة.",
    "specialization_year_mismatch": "⚠️ الاختصاص المحدد لا يتبع السنة الدراسية المختارة.",
    "subject_not_found": "⚠️ المادة غير موجودة.",
    "subject_code_exists": "⚠️ رمز المادة مستخدم مسبقاً. يرجى اختيار رمز آخر.",
    "invalid_subject_code": ("⚠️ رمز المادة غير صالح. يجب أن يتكون من حروف إنجليزية وأرقام فقط، "
                             "ويبدأ بحرف، وطوله بين 2 و20 خانة (مثال: <code>CS101</code>)."),
    "invalid_subject_name": "⚠️ اسم المادة غير صالح. يجب أن يتراوح طوله بين {min} و{max} حرفاً.",
    "subject_has_content": "⚠️ لا يمكن حذف المادة لوجود محتوى مرتبط بها. احذف المحتوى أولاً.",
    "subject_not_assigned": "⛔️ هذه المادة غير مسندة إليك.",
    "invalid_type": "⚠️ نوع المحتوى غير صالح.",
    "invalid_number": "⚠️ الرقم غير صالح. يرجى إدخال رقم صحيح بين 1 و9999.",
    "number_taken": "⛔️ الرقم {number} غير متاح ({state}). اختر رقماً متاحاً.",
    "invalid_semester": "⚠️ الفصل الدراسي غير صالح. اختر الفصل الأول أو الثاني.",
    "duplicate_content": ("⚠️ <b>هذا المحتوى مرفوع مسبقاً.</b>\n"
                          "يوجد سجل بنفس المادة والنوع والرقم. إذا كنت ترغب بتحديثه، "
                          "يرجى التواصل مع الإدارة لطلب التحديث."),
    "invalid_pdf": "⚠️ الملف المرسل ليس ملف PDF. يرجى إرسال ملف بصيغة <code>.pdf</code>.",
    "invalid_tex": "⚠️ الملف المرسل ليس ملف TEX. يرجى إرسال ملف بصيغة <code>.tex</code>.",
    "file_too_large": "⚠️ حجم الملف يتجاوز الحد المسموح ({max_mb} ميغابايت).",
    "invalid_skip_reason": "⚠️ يرجى كتابة سبب واضح لعدم إرفاق ملف PDF (بين {min} و{max} حرفاً).",
    "pdf_required": "⚠️ ملف PDF إلزامي عند إعادة الإرسال.",
    "upload_failed": "⚠️ تعذّر رفع الملفات بسبب خطأ في الاتصال بـ Telegram. لم يتم حفظ الإرسال، يرجى المحاولة مرة أخرى.",
    "operation_interrupted": "⚠️ تمت مقاطعة العملية ولم تكتمل. يرجى المحاولة مرة أخرى.",
    "content_not_found": "⚠️ المحتوى غير موجود أو تم حذفه.",
    "not_rejected": "⚠️ لا يمكن إعادة الإرسال؛ هذا المحتوى ليس في حالة «مرفوض».",
    "not_pending": "⚠️ لم يعد هذا المحتوى بانتظار المراجعة (الحالة الحالية: {status_name}).",
    "approve_failed": "⚠️ تعذّر نقل الملفات إلى القنوات المعتمدة. أُعيد المحتوى إلى قائمة المراجعة، يرجى المحاولة لاحقاً.",
    "invalid_reject_reason": "⚠️ سبب الرفض إلزامي ويجب أن يتراوح طوله بين {min} و{max} حرفاً.",
    "content_busy": "⚠️ هذا المحتوى قيد المعالجة حالياً. يرجى المحاولة بعد قليل.",
    "invalid_support_username": "⚠️ معرّف الدعم غير صالح. أرسل معرّف Telegram صحيحاً (مثال: @ITGenixSupport).",
    "invalid_field": "⚠️ الحقل المطلوب غير صالح.",
    "in_use": "⚠️ لا يمكن تنفيذ العملية لارتباط العنصر ببيانات أخرى.",
    "integrity_error": "⚠️ تعذّر حفظ البيانات بسبب تعارض مع بيانات موجودة.",
}


def error(code: str, **params) -> str:
    template = ERRORS.get(code, UNEXPECTED_ERROR)
    if "status" in params:
        params["status_name"] = STATUS_NAMES.get(params["status"] or "", "غير معروفة")
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        return template


# ───────────── content formatting ─────────────
def content_title(c: Content) -> str:
    return f"{c.subject_code} • {TYPE_NAMES[c.content_type]} {c.number}"


def content_button(c: Content, with_status: bool = False) -> str:
    prefix = f"{STATUS_ICON.get(c.status, '')} " if with_status else ""
    return f"{prefix}{c.subject_code} • {TYPE_NAMES[c.content_type]} {c.number}"


def subject_line(s: Subject) -> str:
    spec = f" • {s.specialization_name}" if s.specialization_name else ""
    return f"{s.year_name}{spec} • {SEMESTER_NAMES.get(s.semester, '')}"


def _file_line(c: Content, kind: str) -> str:
    f = c.file(kind)
    label = "PDF" if kind == "pdf" else "TEX"
    if f:
        return f"📎 ملف {label}: <code>{e(f.file_name or label)}</code>"
    if kind == "pdf" and c.pdf_skip_reason:
        return f"📎 ملف PDF: لم يُرفق — <i>السبب: {e(c.pdf_skip_reason)}</i>"
    return f"📎 ملف {label}: —"


def content_details(c: Content, *, show_student: bool = True, show_files: bool = True) -> str:
    lines = [
        f"📘 <b>{e(c.subject_name)}</b> (<code>{e(c.subject_code)}</code>)",
        f"🎓 {e(c.year_name)}" + (f" • {e(c.specialization_name)}" if c.specialization_name else "")
        + f" • {SEMESTER_NAMES.get(c.semester, '')}",
        f"🗂️ النوع: {TYPE_NAMES[c.content_type]} • الرقم: <b>{c.number}</b>",
        f"📌 الحالة: {STATUS_NAMES.get(c.status, c.status)}",
    ]
    if show_student:
        lines.append(f"👤 الطالب: {e(c.student_name) if c.student_name else 'مستخدم محذوف'}")
    lines.append(f"🕘 تاريخ الإرسال: {fmt_time(c.submitted_at)}")
    if c.decided_at and c.status in ("approved", "rejected"):
        lines.append(f"🧾 تاريخ القرار: {fmt_time(c.decided_at)}")
    if show_files:
        lines += [_file_line(c, "pdf"), _file_line(c, "tex")]
    elif c.pdf_skip_reason:
        lines.append(f"📎 لم يُرفق PDF — <i>السبب: {e(c.pdf_skip_reason)}</i>")
    if c.rejection_reason:
        label = "سبب الرفض" if c.status == "rejected" else "سبب الرفض السابق"
        lines.append(f"\n❗️ <b>{label}:</b> {e(c.rejection_reason)}")
    return "\n".join(lines)


def channel_caption(c: Content, approved: bool) -> str:
    tag = "✅ معتمد" if approved else "⏳ بانتظار المراجعة"
    spec = f" • {c.specialization_name}" if c.specialization_name else ""
    return (f"#ITGX_{c.id} • {tag}\n"
            f"{c.subject_name} ({c.subject_code})\n"
            f"{c.year_name}{spec} • {SEMESTER_NAMES.get(c.semester, '')}\n"
            f"{TYPE_NAMES[c.content_type]} رقم {c.number}")[:1000]


# ───────────── student ─────────────
ST_NO_SUBJECTS = "📚 لا توجد مواد مسندة إليك حالياً. يرجى التواصل مع الإدارة."
ST_SUBJECTS_TITLE = "📚 <b>موادي</b>\n\nاختر مادة لعرض تفاصيلها:"
ST_RECENT_TITLE = "🕘 <b>آخر 5 محاضرات وجلسات تم رفعها</b>"
ST_RECENT_EMPTY = "🕘 لم تقم برفع أي محتوى بعد."
ST_REJECTED_TITLE = "❌ <b>المحاضرات المرفوضة</b>\n\nاختر عنصراً لعرض سبب الرفض وإرفاق ملفات جديدة:"
ST_REJECTED_EMPTY = "✅ لا توجد محاضرات أو جلسات مرفوضة."
ST_PICK_SUBJECT = "📤 <b>رفع محتوى جديد</b>\n\nالخطوة 1 من 5: اختر المادة:"
ST_PICK_TYPE = "📤 <b>{subject}</b>\n\nالخطوة 2 من 5: اختر نوع المحتوى:"
ST_ASK_NUMBER = ("📤 <b>{subject}</b> • {ctype}\n\nالخطوة 3 من 5: اختر رقم {ctype} من الأرقام المتاحة "
                 "(الأرقام {start}–{end}):\n\n{legend}")
ST_NUMBER_REFRESHED = "تم تحديث حالة الأرقام."
ST_EXPECT_NUMBER_BUTTON = "⚠️ يرجى اختيار الرقم من الأزرار."
ST_ASK_PDF = ("📤 <b>{title}</b>\n\nالخطوة 4 من 5: أرسل ملف <b>PDF</b> كمستند.\n"
              "يمكنك تخطي هذه الخطوة بشرط كتابة سبب عدم الإرفاق.")
ST_ASK_SKIP_REASON = "✍️ اكتب سبب عدم إرفاق ملف PDF:"
ST_ASK_TEX = "📤 <b>{title}</b>\n\nالخطوة 5 من 5: أرسل ملف <b>TEX</b> (إلزامي) كمستند بصيغة <code>.tex</code>."
ST_SUMMARY = ("📋 <b>مراجعة الإرسال</b>\n\n📘 المادة: {subject}\n🗂️ النوع: {ctype} • الرقم: <b>{number}</b>\n"
              "{pdf_line}\n📎 ملف TEX: <code>{tex}</code>\n\nهل تريد إرسال المحتوى للمراجعة؟")
ST_SUMMARY_PDF = "📎 ملف PDF: <code>{name}</code>"
ST_SUMMARY_NO_PDF = "📎 ملف PDF: لم يُرفق — <i>السبب: {reason}</i>"
ST_SENDING = "⏳ جارٍ رفع الملفات، يرجى الانتظار..."
ST_SUBMITTED = "✅ <b>تم إرسال المحتوى للمراجعة بنجاح.</b>\n\n{title}\nسيصلك إشعار عند اعتماده أو رفضه."
ST_EXPECT_PDF = "⚠️ يرجى إرسال ملف PDF كمستند، أو الضغط على «تخطي ملف PDF»."
ST_EXPECT_PDF_MANDATORY = "⚠️ يرجى إرسال ملف PDF كمستند (إلزامي عند إعادة الإرسال)."
ST_EXPECT_TEX = "⚠️ يرجى إرسال ملف TEX كمستند بصيغة <code>.tex</code>."
ST_EXPECT_TEXT = "⚠️ يرجى إرسال نص."
ST_SESSION_EXPIRED = "⚠️ انتهت صلاحية هذه الخطوة. يرجى البدء من جديد."
ST_SUBJECT_INFO = ("📘 <b>{name}</b> (<code>{code}</code>)\n🎓 {line}\n\n"
                   "<b>المحاضرات:</b>\n{lectures}\n\n<b>الجلسات:</b>\n{sessions}")
ST_NONE = "لا يوجد"
ST_REJECTED_ITEM = "{details}\n\nلإعادة الإرسال اضغط «إرفاق ملفات جديدة». يجب إرفاق ملفي PDF وTEX معاً."
ST_RESUB_PDF = ("📎 <b>إعادة إرسال: {title}</b>\n\nالخطوة 1 من 2: أرسل ملف <b>PDF</b> الجديد (إلزامي).")
ST_RESUB_TEX = "📎 <b>إعادة إرسال: {title}</b>\n\nالخطوة 2 من 2: أرسل ملف <b>TEX</b> الجديد."
ST_RESUB_SUMMARY = ("📋 <b>مراجعة إعادة الإرسال</b>\n\n{title}\n📎 ملف PDF: <code>{pdf}</code>\n"
                    "📎 ملف TEX: <code>{tex}</code>\n\nسيتم تحديث السجل الحالي وإعادته إلى قائمة المراجعة.")
ST_RESUBMITTED = "✅ <b>تمت إعادة إرسال المحتوى للمراجعة بنجاح.</b>\n\n{title}"


def number_list(nums: list[int] | None) -> str:
    return "، ".join(str(n) for n in nums) if nums else ST_NONE


def subject_summary_block(summary: dict[str, list[int]] | None) -> str:
    summary = summary or {}
    return (f"✅ معتمدة: {number_list(summary.get('approved'))}\n"
            f"⏳ قيد المراجعة: {number_list((summary.get('pending') or []) + (summary.get('approving') or []))}\n"
            f"❌ مرفوضة: {number_list(summary.get('rejected'))}")


def recent_list(items: list[Content]) -> str:
    rows = [ST_RECENT_TITLE, ""]
    for c in items:
        rows.append(f"{STATUS_ICON.get(c.status, '')} {e(c.subject_name)} — {TYPE_NAMES[c.content_type]} {c.number}"
                    f"\n    {STATUS_NAMES.get(c.status, c.status)} • {fmt_time(c.submitted_at)}")
    return "\n".join(rows)


# ───────────── review ─────────────
RV_PENDING_TITLE = "📝 <b>المحاضرات التي تتطلب مراجعة</b> ({total})\n\nاختر عنصراً لمراجعته:"
RV_PENDING_EMPTY = "✅ لا توجد محاضرات أو جلسات بانتظار المراجعة."
RV_APPROVED_EMPTY = "لا يوجد محتوى معتمد في هذا القسم."
AP_TITLE = "✅ <b>المحاضرات والجلسات المعتمدة</b>"
AP_YEARS = AP_TITLE + "\n\nاختر السنة الدراسية (الرقم بين القوسين = عدد العناصر المعتمدة):"
AP_SPECS = AP_TITLE + "\n📍 {path}\n\nاختر الاختصاص:"
AP_SEMESTERS = AP_TITLE + "\n📍 {path}\n\nاختر الفصل الدراسي:"
AP_SUBJECTS = AP_TITLE + "\n📍 {path}\n\nاختر المادة:"
AP_TYPES = AP_TITLE + "\n📍 {path}\n\nاختر نوع المحتوى:"
AP_LIST = AP_TITLE + "\n📍 {path}\n\n{ctype} المعتمدة ({total}):"
AP_NO_SPECS = "لا توجد اختصاصات في هذه السنة بعد."
AP_NO_SUBJECTS = "لا توجد مواد في هذا الفصل."
RV_CONFIRM_APPROVE = ("❓ <b>تأكيد الاعتماد</b>\n\n{title}\n\nسيتم نقل الملفات إلى القنوات المعتمدة وإشعار الطالب.")
RV_ASK_REJECT = "✍️ اكتب سبب رفض <b>{title}</b> (إلزامي):"
RV_APPROVING = "⏳ جارٍ اعتماد المحتوى ونقل الملفات..."
RV_APPROVED_DONE = "✅ <b>تم اعتماد المحتوى بنجاح.</b>\n\n{title}"
RV_REJECTED_DONE = "❌ <b>تم رفض المحتوى وإشعار الطالب.</b>\n\n{title}\nالسبب: {reason}"
RV_FILES_SENT = "📄 تم إرسال {sent} ملف."
RV_FILES_PARTIAL = "⚠️ تم إرسال {sent} ملف، وتعذّر إرسال {failed}."
RV_NO_FILES = "⚠️ لا توجد ملفات مرتبطة بهذا المحتوى."
RV_NEW_SUBMISSION = "🆕 <b>محتوى جديد بانتظار المراجعة</b>\n\n{title}\n👤 الطالب: {student}"
RV_RESUBMISSION = "🔁 <b>إعادة إرسال محتوى مرفوض بانتظار المراجعة</b>\n\n{title}\n👤 الطالب: {student}"
RV_BTN_OPEN = "🔍 فتح للمراجعة"
NOTIFY_APPROVED = "✅ <b>تم اعتماد المحتوى الخاص بك</b>\n\n{title}\n📘 {subject}"
NOTIFY_REJECTED = ("❌ <b>تم رفض المحتوى الخاص بك</b>\n\n{title}\n📘 {subject}\n\n❗️ <b>سبب الرفض:</b> {reason}\n\n"
                   "يمكنك إرفاق ملفات جديدة من قسم «المحاضرات المرفوضة».")
NOTIFY_ROLLED_BACK_UPLOAD = "⚠️ تعذّر إكمال رفع المحتوى رقم #{cid} بسبب انقطاع مفاجئ. يرجى إعادة الإرسال."
NOTIFY_ROLLED_BACK_RESUB = "⚠️ تعذّر إكمال إعادة إرسال المحتوى رقم #{cid}. ما زال المحتوى مرفوضاً، يرجى إعادة المحاولة."
BTN_OPEN_REJECTED = "❌ فتح المحتوى المرفوض"

# ───────────── admin: users ─────────────
AD_USERS_MENU = "👥 <b>إدارة المستخدمين</b>"
AD_ASK_TID = ("➕ <b>إضافة مستخدم</b>\n\nأرسل معرّف Telegram الرقمي للمستخدم (Telegram ID).\n"
              "<i>يمكن للمستخدم معرفة معرّفه بإرسال /start للبوت، إذ ستظهر له رسالة تتضمن معرّفه.</i>")
AD_ASK_NAME = "✍️ أرسل الاسم الكامل للمستخدم <code>{tid}</code>:"
AD_ASK_ROLE = "🎭 اختر دور المستخدم <b>{name}</b>:"
AD_USER_ADDED = "✅ تمت إضافة المستخدم <b>{name}</b> بدور «{role}»."
AD_USER_ADDED_STUDENT = "\n\nيمكنك الآن إسناد المواد له من زر «المواد المسندة»."
AD_USERS_FILTER = "📋 <b>عرض المستخدمين</b>\n\nاختر الفئة:"
AD_USERS_LIST = "📋 <b>{title}</b> ({total}):"
AD_USER_DETAILS = ("👤 <b>{name}</b>\n🆔 المعرّف: <code>{tid}</code>\n🎭 الدور: {role}\n"
                   "🕘 تاريخ الإضافة: {created}{extra}")
AD_USER_SUBJECTS_COUNT = "\n📚 عدد المواد المسندة: {n}"
AD_USER_PROTECTED = "\n🔒 مدير أساسي (محدد في إعدادات الخادم)"
AD_PICK_ROLE = "🔁 اختر الدور الجديد للمستخدم <b>{name}</b>:"
AD_ROLE_CHANGED = "✅ تم تغيير دور المستخدم إلى «{role}»."
AD_ROLE_CHANGE_NOTE = "\n<i>ملاحظة: عند تغيير دور الطالب تُلغى المواد المسندة إليه.</i>"
AD_ASK_RENAME = "✍️ أرسل الاسم الجديد للمستخدم <b>{name}</b>:"
AD_RENAMED = "✅ تم تعديل الاسم."
AD_CONFIRM_REMOVE = ("⚠️ <b>تأكيد حذف المستخدم</b>\n\n👤 {name}\n🆔 <code>{tid}</code>\n🎭 {role}\n\n"
                     "سيفقد المستخدم صلاحية الوصول إلى البوت فوراً. يبقى المحتوى الذي رفعه محفوظاً.")
AD_REMOVED = "✅ تم حذف المستخدم."
AD_ASSIGN_TITLE = "📚 <b>إسناد المواد إلى: {name}</b>\n\nاختر السنة الدراسية:"
AD_ASSIGN_SPEC = "📚 <b>إسناد المواد إلى: {name}</b>\n{year}\n\nاختر الاختصاص:"
AD_ASSIGN_SUBJECTS = "📚 <b>إسناد المواد إلى: {name}</b>\n{line}\n\nاضغط على المادة لإسنادها أو إلغاء إسنادها (✅ = مسندة):"
AD_ASSIGN_CURRENT = "\n\n<b>المواد المسندة حالياً:</b>\n{subjects}"
AD_NO_SPECS = "⚠️ لا توجد اختصاصات في هذه السنة. أضف اختصاصاً من «الإدارة الأكاديمية» أولاً."
AD_NO_SUBJECTS = "لا توجد مواد في هذا القسم."

# ───────────── admin: academic ─────────────
AD_ACADEMIC_MENU = "🎓 <b>الإدارة الأكاديمية</b>"
AD_YEARS_TITLE = ("📅 <b>السنوات الدراسية والاختصاصات</b>\n\n"
                  "السنوات الأولى والثانية والثالثة لا تتطلب اختصاصاً، أما الرابعة والخامسة فالاختصاص فيهما إلزامي.\n"
                  "اختر السنة:")
AD_YEAR_NO_SPEC = "📅 <b>{year}</b>\n\nهذه السنة لا تتطلب اختصاصاً. تُضاف موادها مباشرة من قسم «المواد»."
AD_YEAR_SPECS = "📅 <b>{year}</b> — الاختصاصات ({n}):"
AD_ASK_SPEC_NAME = "✍️ أرسل اسم الاختصاص الجديد في <b>{year}</b>:"
AD_SPEC_ADDED = "✅ تمت إضافة الاختصاص."
AD_SPEC_DETAILS = "🧭 <b>{name}</b>\n📅 {year}\n📖 عدد المواد: {n}"
AD_ASK_SPEC_RENAME = "✍️ أرسل الاسم الجديد للاختصاص <b>{name}</b>:"
AD_SPEC_RENAMED = "✅ تم تعديل اسم الاختصاص."
AD_CONFIRM_DELETE_SPEC = "⚠️ هل تريد حذف الاختصاص <b>{name}</b> نهائياً؟"
AD_SPEC_DELETED = "✅ تم حذف الاختصاص."
AD_SUBJECTS_YEAR = "📖 <b>المواد</b>\n\nاختر السنة الدراسية لعرض موادها أو إضافة مادة جديدة:"
AD_SUBJECTS_SPEC = "📖 <b>{year}</b>\n\nاختر الاختصاص:"
AD_SUBJECTS_SEMESTER = "📖 <b>{line}</b>\n\nاختر الفصل الدراسي لعرض مواده أو إضافة مادة جديدة:"
AD_SUBJECTS_LIST = "📖 <b>{line}</b> — المواد ({n}):"
AD_SUBJECT_DETAILS = ("📘 <b>{name}</b>\n🔤 الرمز: <code>{code}</code>\n🎓 {line}\n"
                      "👥 الطلاب المسندون: {students}\n🗂️ عدد السجلات: {contents}")
AD_SUBJECT_UNCONFIRMED_NOTE = ("\n\n⚠️ <b>تنبيه:</b> أُسند هذا الفصل تلقائياً أثناء ترقية النظام. "
                               "يرجى تأكيده أو تغييره.")
AD_PICK_SEMESTER = "🗓️ اختر الفصل الدراسي للمادة <b>{name}</b> (الحالي: {current}):"
AD_UNCONFIRMED_TITLE = ("⚠️ <b>مواد بحاجة لتأكيد الفصل الدراسي</b>\n\n"
                        "أُضيفت هذه المواد قبل اعتماد الفصول، فأُسندت مؤقتاً إلى الفصل الأول دون فقدان أي بيانات. "
                        "افتح كل مادة لتأكيد الفصل أو تغييره:")
AD_ASK_SUBJECT_NAME = "➕ <b>إضافة مادة</b>\n🎓 {line}\n\n✍️ أرسل اسم المادة:"
AD_ASK_SUBJECT_CODE = ("🔤 أرسل رمز المادة <b>{name}</b>.\nحروف إنجليزية وأرقام فقط، يبدأ بحرف (مثال: <code>CS101</code>).")
AD_SUBJECT_CREATED = "✅ تم إنشاء المادة <b>{name}</b> (<code>{code}</code>)\n🎓 {line}"
AD_ASK_SUBJECT_NEW_NAME = "✍️ أرسل الاسم الجديد للمادة <b>{name}</b>:"
AD_ASK_SUBJECT_NEW_CODE = "🔤 أرسل الرمز الجديد للمادة <b>{name}</b> (الرمز الحالي: <code>{code}</code>):"
AD_SUBJECT_UPDATED = "✅ تم تحديث المادة."
AD_CONFIRM_DELETE_SUBJECT = ("⚠️ هل تريد حذف المادة <b>{name}</b> (<code>{code}</code>) نهائياً؟\n"
                             "سيتم إلغاء إسنادها من جميع الطلاب.")
AD_SUBJECT_DELETED = "✅ تم حذف المادة."

# ───────────── admin: content ─────────────
AD_CONTENT_MENU = "🗂️ <b>إدارة المحتوى</b>"
AD_ASK_SEARCH_CODE = "🔍 <b>البحث عن محتوى</b>\n\nالخطوة 1 من 3: أرسل رمز المادة (مثال: <code>CS101</code>):"
AD_SEARCH_TYPE = "🔍 <b>{subject}</b>\n\nالخطوة 2 من 3: اختر نوع المحتوى:"
AD_SEARCH_NUMBER = "🔍 <b>{subject}</b> • {ctype}\n\nالخطوة 3 من 3: أرسل الرقم، أو اضغط «عرض الكل»:"
AD_SEARCH_RESULTS = "🔍 <b>نتائج البحث</b> — {subject} ({total}):"
AD_SEARCH_EMPTY = "🔍 لا توجد نتائج مطابقة."
AD_CONFIRM_DELETE = ("⚠️ <b>تأكيد الحذف النهائي</b>\n\n{details}\n\n"
                     "سيتم حذف:\n• سجل المحتوى من قاعدة البيانات\n• ملفات PDF وTEX من القنوات المعتمدة والمؤقتة\n"
                     "• نسخ المراجعة والملفات المرفوضة المرتبطة\n\nبعد الحذف يصبح هذا الرقم متاحاً لإرسال جديد. "
                     "<b>لا يمكن التراجع عن هذه العملية.</b>")
AD_DELETING = "⏳ جارٍ حذف المحتوى وجميع ملفاته..."
AD_DELETE_DONE = "✅ <b>تم الحذف بالكامل.</b>\n\n{title}\nتم حذف السجل و{done} رسالة مرتبطة من Telegram."
AD_DELETE_PARTIAL = ("⚠️ <b>تم حذف السجل، لكن الحذف لم يكتمل بعد.</b>\n\n{title}\n"
                     "• رسائل محذوفة: {done}\n• قيد إعادة المحاولة تلقائياً: {pending}\n• متعثرة: {failed}\n\n"
                     "ستتم إعادة المحاولة تلقائياً وسيصلك إشعار عند الاكتمال. "
                     "تأكد من صلاحيات البوت في القنوات.")
AD_JOB_DONE = "✅ <b>اكتمل الحذف بالكامل</b> (عملية #{job})\n\n{title}\nتم حذف جميع الملفات المرتبطة ({done})."
AD_JOB_ATTENTION = ("⚠️ <b>عملية الحذف #{job} تحتاج إلى تدخل</b>\n\n{title}\n• محذوفة: {done}\n• متعثرة: {failed}\n\n"
                    "تحقق من صلاحيات البوت في القنوات، ثم استخدم «إعادة محاولة العمليات المتعثرة» من قسم إدارة المحتوى.")
AD_CLEANUP_STATUS = ("🧹 <b>عمليات الحذف والتنظيف</b>\n\n"
                     "• بانتظار الحذف: {pending}\n• متعثرة (تجاوزت عدد المحاولات): {failed}\n"
                     "• محجوزة لعمليات جارية: {held}\n• منجزة (آخر 30 يوماً): {done}\n\n"
                     "• عمليات حذف جارية: {jobs_in_progress}\n• عمليات تحتاج تدخلاً: {jobs_needs_attention}{failed_list}")
AD_FAILED_HEADER = "\n\n<b>أمثلة على العناصر المتعثرة:</b>"
AD_FAILED_ITEM = "\n• <code>{chat}</code>/<code>{mid}</code> — {error}"
AD_RETRIED = "🔁 تمت إعادة جدولة {n} عنصر للمحاولة."
AD_CLEANUP_RAN = "▶️ تمت معالجة {n} عنصر."

# ───────────── admin: settings ─────────────
AD_SETTINGS_MENU = "⚙️ <b>الإعدادات</b>"
AD_CHANNELS = "🔎 <b>فحص القنوات</b>\n\n{rows}\n{note}"
AD_CHANNEL_NAMES = {"temp_pdf": "قناة PDF المؤقتة", "temp_tex": "قناة TEX المؤقتة",
                    "approved_pdf": "قناة PDF المعتمدة", "approved_tex": "قناة TEX المعتمدة"}
AD_CHANNEL_POLICY = {"approved": "• حماية المحتوى: 🔒 دائمة (محتوى الطلاب)\n",
                     "temp": "• حماية المحتوى: 🔓 بدون قيود (مراجعة مسؤولي الرفع)\n"}
AD_PROTECTION_NOTE = ("🔒 <b>حماية محتوى الطلاب دائمة ولا يمكن إيقافها.</b>\n"
                      "كل ما يرسله البوت للطلاب، ومنشورات القناتين المعتمدتين، يُرسل بخاصية Telegram "
                      "(protect_content) التي تمنع إعادة التوجيه والحفظ والتنزيل، وتمنع لقطات الشاشة في تطبيقات "
                      "الهاتف الرسمية. المدير ومسؤولو الرفع يستلمون الملفات داخل البوت دون قيود.\n"
                      "⚠️ لا يضمن Telegram منع لقطات الشاشة في تطبيقات سطح المكتب والويب، ولا يمنع التصوير بجهاز آخر.")
AD_PROTECTION_PENDING = "\n⏳ ملفات منشورة سابقاً قيد إعادة النشر لتطبيق القاعدة: {n} (تتم المحاولة تلقائياً)."
AD_PROTECTION_NOT_HONOURED = "\n⚠️ ملفات طُلبت حمايتها ولم يؤكدها Telegram: {n}"
AD_CHANNEL_ROW = ("<b>{label}</b> (<code>{cid}</code>)\n• الاسم: {title}\n• صلاحية النشر: {post}\n"
                  "• صلاحية الحذف: {delete}\n• تقييد حفظ المحتوى في القناة: {protected}\n")
AD_CHANNEL_ERROR = "<b>{label}</b> (<code>{cid}</code>)\n• ⚠️ تعذّر الوصول: {error}\n"
AD_SUPPORT_SETTINGS = "🆘 <b>إعدادات الدعم الفني</b>\n\nالمعرّف الحالي: {current}"
AD_ASK_SUPPORT = "✍️ أرسل معرّف Telegram للدعم الفني (مثال: @ITGenixSupport):"
AD_SUPPORT_SAVED = "✅ تم حفظ معرّف الدعم: @{username}"


def number_button(number: int, category: str) -> str:
    icon = NUMBER_ICON.get(category, "")
    return f"{icon}{number}" if icon else str(number)


def path(*parts: str | None) -> str:
    return " ← ".join(e(p) for p in parts if p)


def yes_no(flag: bool) -> str:
    return "نعم ✅" if flag else "لا ❌"


def user_label(u: AppUser) -> str:
    return f"{u.full_name} • {ROLE_NAMES[u.role]}"
