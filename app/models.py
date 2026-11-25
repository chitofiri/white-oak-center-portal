from datetime import datetime, timezone
import enum
from sqlalchemy import String, DateTime, Boolean, ForeignKey, Text, Enum, Integer, Date, Time, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def utcnow():
    return datetime.now(timezone.utc)

class Role(str, enum.Enum):
    administrator = "administrator"
    staff = "staff"
    safeguarding_lead = "safeguarding_lead"
    client = "client"

class PartyType(str, enum.Enum):
    parent = "parent"
    guardian = "guardian"
    child_representative = "child_representative"
    solicitor = "solicitor"
    social_worker = "social_worker"
    other = "other"

class DocumentVisibility(str, enum.Enum):
    staff_only = "staff_only"
    assigned_party = "assigned_party"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(180))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.client)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enrolled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class CaseRecord(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    case_title: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(40), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

class CaseParty(Base):
    """A named portal account's explicit, case-specific access grant."""
    __tablename__ = "case_parties"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    party_type: Mapped[PartyType] = mapped_column(Enum(PartyType))
    relationship_label: Mapped[str] = mapped_column(String(100))
    can_view_documents: Mapped[bool] = mapped_column(Boolean, default=False)
    can_view_schedule: Mapped[bool] = mapped_column(Boolean, default=False)
    can_submit_documents: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ReferralSubmission(Base):
    __tablename__ = "referral_submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    form_data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40), default="submitted")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ContactSession(Base):
    __tablename__ = "contact_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    session_date: Mapped[Date] = mapped_column(Date)
    start_time: Mapped[Time] = mapped_column(Time)
    end_time: Mapped[Time] = mapped_column(Time)
    venue_label: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default="proposed")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class DocumentRecord(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recipient_party_id: Mapped[int | None] = mapped_column(ForeignKey("case_parties.id"), nullable=True)
    visibility: Mapped[DocumentVisibility] = mapped_column(Enum(DocumentVisibility), default=DocumentVisibility.staff_only)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(100), default="application/pdf")
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class SafeguardingNote(Base):
    __tablename__ = "safeguarding_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note_text: Mapped[str] = mapped_column(Text)
    access_reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    object_type: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(String(80))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Never store document contents, passwords, tokens or safeguarding narrative here.
    metadata_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
