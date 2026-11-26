"""Plain domain models shared between layers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    UPLOADER = "uploader"
    STUDENT = "student"


class ContentType(str, Enum):
    LECTURE = "lecture"
    SESSION = "session"


class Status(str, Enum):
    UPLOADING = "uploading"
    PENDING = "pending"
    APPROVING = "approving"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESUBMITTING = "resubmitting"


TRANSITIONAL = (Status.UPLOADING.value, Status.APPROVING.value, Status.RESUBMITTING.value)
DELETABLE = (Status.PENDING.value, Status.APPROVED.value, Status.REJECTED.value)
SEMESTERS = (1, 2)


def number_category(status: str | None) -> str:
    """Display category of a content number: approved / pending / rejected / available."""
    if status is None:
        return "available"
    if status in (Status.APPROVED.value, Status.REJECTED.value):
        return status
    return "pending"   # pending + every in-flight state keeps the number occupied


@dataclass(frozen=True)
class AppUser:
    telegram_id: int
    full_name: str
    role: str
    created_at: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value


@dataclass(frozen=True)
class Year:
    id: int
    name: str
    requires_specialization: bool


@dataclass(frozen=True)
class Specialization:
    id: int
    year_id: int
    name: str


@dataclass(frozen=True)
class Subject:
    id: int
    code: str
    name: str
    year_id: int
    year_name: str
    specialization_id: int | None
    specialization_name: str | None
    semester: int = 1
    semester_confirmed: bool = True


@dataclass(frozen=True)
class FileInfo:
    """A Telegram document received from a user (kept in FSM until submission)."""
    file_id: str
    file_unique_id: str
    file_name: str
    file_size: int

    def to_dict(self) -> dict:
        return {"file_id": self.file_id, "file_unique_id": self.file_unique_id,
                "file_name": self.file_name, "file_size": self.file_size}

    @classmethod
    def from_dict(cls, d: dict | None) -> "FileInfo | None":
        return cls(**d) if d else None


@dataclass(frozen=True)
class ContentFile:
    content_id: int
    kind: str
    stage: str
    chat_id: int
    message_id: int
    file_id: str
    file_name: str | None
    file_size: int | None
    protect_requested: bool = False
    protected: bool | None = None      # flag reported by Telegram; None = unknown (posted before v2)


@dataclass(frozen=True)
class Sent:
    """Result of posting a document: Telegram's message id and its reported protection flag."""
    message_id: int
    protected: bool


@dataclass(frozen=True)
class Content:
    id: int
    subject_id: int
    subject_code: str
    subject_name: str
    year_name: str
    specialization_name: str | None
    content_type: str
    number: int
    student_id: int | None
    student_name: str | None
    status: str
    pdf_skip_reason: str | None
    rejection_reason: str | None
    reviewer_id: int | None
    reviewer_name: str | None
    submitted_at: str
    decided_at: str | None
    files: tuple[ContentFile, ...] = ()
    semester: int = 1

    def file(self, kind: str) -> ContentFile | None:
        return next((f for f in self.files if f.kind == kind), None)


@dataclass(frozen=True)
class QueueItem:
    id: int
    chat_id: int
    message_id: int
    reason: str
    job_id: int | None
    attempts: int


@dataclass(frozen=True)
class DeletionReport:
    job_id: int
    description: str
    total: int
    done: int
    pending: int
    failed: int

    @property
    def complete(self) -> bool:
        return self.pending == 0 and self.failed == 0
