from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select
from .config import settings
from .database import Base, engine, get_db
from .models import (
    User, Role, CaseRecord, CaseParty, PartyType, ReferralSubmission,
    ContactSession, DocumentRecord, DocumentVisibility, SafeguardingNote, AuditEvent
)
from .schemas import (
    LoginInput, UserCreate, UserView, CaseCreate, CaseView,
    CasePartyCreate, ReferralCreate, ContactSessionCreate, SafeguardingNoteCreate
)
from .security import verify_password, hash_password, create_access_token, current_user, require_roles

app = FastAPI(title=settings.app_name, docs_url="/docs" if settings.environment == "development" else None)
Base.metadata.create_all(bind=engine)  # Development only; production must use reviewed Alembic migrations.
Path(settings.private_upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/web", StaticFiles(directory="web"), name="web")

STAFF_ROLES = (Role.administrator, Role.staff, Role.safeguarding_lead)
CASE_STAFF = (Role.administrator, Role.staff)
SAFEGUARDING_ROLES = (Role.administrator, Role.safeguarding_lead)

def audit(db: Session, actor: User, action: str, object_type: str, object_id: str, summary: str | None = None):
    db.add(AuditEvent(actor_user_id=actor.id, action=action, object_type=object_type,
                      object_id=str(object_id), metadata_summary=summary))

def require_case_staff(db: Session, case_id: int):
    case = db.get(CaseRecord, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    return case

def party_for_user(db: Session, case_id: int, user_id: int):
    return db.scalar(select(CaseParty).where(
        CaseParty.case_id == case_id, CaseParty.user_id == user_id, CaseParty.is_active.is_(True)
    ))

def client_case_or_404(db: Session, case_id: int, user: User):
    party = party_for_user(db, case_id, user.id)
    if not party:
        # Avoid disclosing whether another person's case exists.
        raise HTTPException(status_code=404, detail="Case not found.")
    case = db.get(CaseRecord, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    return case, party

@app.get("/")
def home():
    return FileResponse("web/index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "environment": settings.environment}

@app.post("/api/auth/login")
def login(data: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    # Production must use an approved identity/MFA solution and secure HttpOnly cookie sessions.
    return {"access_token": create_access_token(user.id), "token_type": "bearer",
            "user": UserView.model_validate(user).model_dump(mode="json")}

@app.get("/api/auth/me", response_model=UserView)
def me(user: User = Depends(current_user)):
    return user

@app.post("/api/admin/users", response_model=UserView)
def create_user(data: UserCreate, db: Session = Depends(get_db),
                admin: User = Depends(require_roles(Role.administrator, Role.staff))):
    # Staff may create client accounts only. Elevated staff roles remain administrator-controlled.
    if admin.role == Role.staff and data.role != Role.client:
        raise HTTPException(status_code=403, detail="Staff may create client accounts only.")
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    try:
        user = User(email=email, full_name=data.full_name, password_hash=hash_password(data.password), role=data.role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.add(user)
    db.flush()
    audit(db, admin, "user.created", "user", user.id, f"role={user.role.value}")
    db.commit()
    db.refresh(user)
    return user

def next_case_number(db: Session) -> str:
    # Suitable for a single-process development database only. Use a database sequence
    # or transaction-safe allocator before production deployment.
    year = datetime.now(timezone.utc).year
    count = db.query(CaseRecord).filter(CaseRecord.case_number.like(f"WOC-{year}-%")).count() + 1
    return f"WOC-{year}-{count:04d}"

@app.post("/api/admin/cases", response_model=CaseView)
def create_case(data: CaseCreate, db: Session = Depends(get_db),
                actor: User = Depends(require_roles(*CASE_STAFF))):
    case = CaseRecord(case_number=next_case_number(db), case_title=data.case_title, created_by_id=actor.id)
    db.add(case)
    db.flush()
    audit(db, actor, "case.created", "case", case.id)
    db.commit()
    db.refresh(case)
    return case

@app.get("/api/admin/cases", response_model=list[CaseView])
def list_cases(db: Session = Depends(get_db),
               actor: User = Depends(require_roles(*STAFF_ROLES))):
    return list(db.scalars(select(CaseRecord).order_by(CaseRecord.created_at.desc())).all())

@app.post("/api/admin/cases/{case_id}/parties")
def grant_case_access(case_id: int, data: CasePartyCreate, db: Session = Depends(get_db),
                      actor: User = Depends(require_roles(*CASE_STAFF))):
    require_case_staff(db, case_id)
    target = db.get(User, data.user_id)
    if not target or not target.is_active or target.role != Role.client:
        raise HTTPException(status_code=404, detail="Active client account not found.")
    existing = party_for_user(db, case_id, target.id)
    if existing:
        raise HTTPException(status_code=409, detail="This account already has active access to the case.")
    party = CaseParty(case_id=case_id, user_id=target.id, party_type=data.party_type,
                      relationship_label=data.relationship_label,
                      can_view_documents=data.can_view_documents,
                      can_view_schedule=data.can_view_schedule,
                      can_submit_documents=data.can_submit_documents,
                      granted_by_id=actor.id)
    db.add(party)
    db.flush()
    audit(db, actor, "case.access_granted", "case_party", party.id,
          f"user_id={target.id};party_type={data.party_type.value}")
    db.commit()
    return {"membership_id": party.id, "case_id": case_id, "user_id": target.id,
            "permissions": {"documents": party.can_view_documents, "schedule": party.can_view_schedule,
                            "submit_documents": party.can_submit_documents}}

@app.delete("/api/admin/cases/{case_id}/parties/{membership_id}")
def revoke_case_access(case_id: int, membership_id: int, db: Session = Depends(get_db),
                       actor: User = Depends(require_roles(*CASE_STAFF))):
    party = db.get(CaseParty, membership_id)
    if not party or party.case_id != case_id or not party.is_active:
        raise HTTPException(status_code=404, detail="Active case access grant not found.")
    party.is_active = False
    audit(db, actor, "case.access_revoked", "case_party", party.id, f"user_id={party.user_id}")
    db.commit()
    return {"message": "Case access revoked."}

@app.get("/api/client/cases")
def client_cases(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.client))):
    memberships = db.scalars(select(CaseParty).where(
        CaseParty.user_id == user.id, CaseParty.is_active.is_(True)
    )).all()
    output = []
    for membership in memberships:
        case = db.get(CaseRecord, membership.case_id)
        if case:
            output.append({"id": case.id, "case_number": case.case_number, "case_title": case.case_title,
                           "status": case.status, "permissions": {
                               "documents": membership.can_view_documents,
                               "schedule": membership.can_view_schedule,
                               "submit_documents": membership.can_submit_documents}})
    return output

@app.post("/api/client/cases/{case_id}/referrals")
def submit_referral(case_id: int, data: ReferralCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.client))):
    _, party = client_case_or_404(db, case_id, user)
    if not party.can_submit_documents:
        raise HTTPException(status_code=403, detail="You are not authorized to submit information for this case.")
    referral = ReferralSubmission(case_id=case_id, submitted_by_id=user.id, form_data=data.form_data)
    db.add(referral)
    db.flush()
    audit(db, user, "referral.submitted", "referral", referral.id)
    db.commit()
    return {"id": referral.id, "status": referral.status, "message": "Referral information submitted."}

@app.get("/api/admin/cases/{case_id}/referrals")
def list_referrals(case_id: int, db: Session = Depends(get_db),
                   actor: User = Depends(require_roles(*STAFF_ROLES))):
    require_case_staff(db, case_id)
    items = db.scalars(select(ReferralSubmission).where(
        ReferralSubmission.case_id == case_id).order_by(ReferralSubmission.submitted_at.desc())).all()
    audit(db, actor, "referrals.viewed", "case", case_id)
    db.commit()
    return [{"id": item.id, "submitted_by_id": item.submitted_by_id, "form_data": item.form_data,
             "status": item.status, "submitted_at": item.submitted_at.isoformat()} for item in items]

@app.post("/api/admin/cases/{case_id}/sessions")
def create_contact_session(case_id: int, data: ContactSessionCreate, db: Session = Depends(get_db),
                            actor: User = Depends(require_roles(*CASE_STAFF))):
    require_case_staff(db, case_id)
    if data.end_time <= data.start_time:
        raise HTTPException(status_code=422, detail="Session end time must be after start time.")
    session = ContactSession(case_id=case_id, session_date=data.session_date,
                             start_time=data.start_time, end_time=data.end_time,
                             venue_label=data.venue_label, created_by_id=actor.id)
    db.add(session)
    db.flush()
    audit(db, actor, "contact_session.created", "contact_session", session.id)
    db.commit()
    return {"id": session.id, "status": session.status}

@app.get("/api/client/cases/{case_id}/sessions")
def client_sessions(case_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.client))):
    _, party = client_case_or_404(db, case_id, user)
    if not party.can_view_schedule:
        raise HTTPException(status_code=403, detail="You are not authorized to view contact arrangements.")
    sessions = db.scalars(select(ContactSession).where(
        ContactSession.case_id == case_id, ContactSession.status != "cancelled"
    ).order_by(ContactSession.session_date, ContactSession.start_time)).all()
    audit(db, user, "contact_sessions.viewed", "case", case_id)
    db.commit()
    return [{"id": s.id, "date": s.session_date.isoformat(), "start_time": s.start_time.isoformat(),
             "end_time": s.end_time.isoformat(), "venue": s.venue_label, "status": s.status} for s in sessions]

@app.post("/api/admin/cases/{case_id}/documents")
async def upload_pdf(case_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                     actor: User = Depends(require_roles(*CASE_STAFF))):
    require_case_staff(db, case_id)
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Only PDF documents are accepted.")
    max_bytes = settings.max_pdf_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"PDF exceeds the {settings.max_pdf_mb} MB limit.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF.")
    key = f"{uuid4().hex}.pdf"
    (Path(settings.private_upload_dir) / key).write_bytes(content)
    record = DocumentRecord(case_id=case_id, uploaded_by_id=actor.id,
                            original_filename=Path(file.filename or "document.pdf").name[:255],
                            storage_key=key, size_bytes=len(content),
                            visibility=DocumentVisibility.staff_only)
    db.add(record)
    db.flush()
    audit(db, actor, "document.uploaded", "document", record.id)
    db.commit()
    return {"id": record.id, "filename": record.original_filename, "visibility": "staff_only"}

@app.post("/api/admin/cases/{case_id}/documents/{document_id}/share")
def share_document(case_id: int, document_id: int, membership_id: int, db: Session = Depends(get_db),
                   actor: User = Depends(require_roles(*CASE_STAFF))):
    record = db.get(DocumentRecord, document_id)
    party = db.get(CaseParty, membership_id)
    if not record or record.case_id != case_id or not party or party.case_id != case_id or not party.is_active:
        raise HTTPException(status_code=404, detail="Document or active case access grant not found.")
    if not party.can_view_documents:
        raise HTTPException(status_code=403, detail="This account has not been granted document access.")
    record.visibility = DocumentVisibility.assigned_party
    record.recipient_party_id = party.id
    audit(db, actor, "document.shared", "document", record.id, f"membership_id={party.id}")
    db.commit()
    return {"message": "Document shared with the selected authorized case account."}

@app.get("/api/client/cases/{case_id}/documents")
def client_documents(case_id: int, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.client))):
    _, party = client_case_or_404(db, case_id, user)
    if not party.can_view_documents:
        raise HTTPException(status_code=403, detail="You are not authorized to view documents.")
    docs = db.scalars(select(DocumentRecord).where(
        DocumentRecord.case_id == case_id,
        DocumentRecord.visibility == DocumentVisibility.assigned_party,
        DocumentRecord.recipient_party_id == party.id
    ).order_by(DocumentRecord.created_at.desc())).all()
    audit(db, user, "client_documents.viewed", "case", case_id)
    db.commit()
    return [{"id": d.id, "filename": d.original_filename, "uploaded_at": d.created_at.isoformat()}
            for d in docs]

@app.get("/api/client/documents/{document_id}/download")
def client_download_document(document_id: int, db: Session = Depends(get_db),
                             user: User = Depends(require_roles(Role.client))):
    record = db.get(DocumentRecord, document_id)
    if not record or record.visibility != DocumentVisibility.assigned_party or not record.recipient_party_id:
        raise HTTPException(status_code=404, detail="Document not found.")
    party = db.get(CaseParty, record.recipient_party_id)
    if not party or not party.is_active or party.user_id != user.id or not party.can_view_documents:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = Path(settings.private_upload_dir) / record.storage_key
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file not found.")
    audit(db, user, "document.downloaded", "document", record.id)
    db.commit()
    return FileResponse(path, media_type="application/pdf", filename=record.original_filename)

@app.post("/api/admin/cases/{case_id}/safeguarding-notes")
def create_safeguarding_note(case_id: int, data: SafeguardingNoteCreate, db: Session = Depends(get_db),
                             actor: User = Depends(require_roles(*SAFEGUARDING_ROLES))):
    require_case_staff(db, case_id)
    note = SafeguardingNote(case_id=case_id, author_id=actor.id,
                            note_text=data.note_text, access_reason=data.access_reason)
    db.add(note)
    db.flush()
    audit(db, actor, "safeguarding_note.created", "safeguarding_note", note.id)
    db.commit()
    return {"id": note.id, "message": "Restricted safeguarding note recorded."}

@app.get("/api/admin/cases/{case_id}/safeguarding-notes")
def read_safeguarding_notes(case_id: int, access_reason: str, db: Session = Depends(get_db),
                            actor: User = Depends(require_roles(*SAFEGUARDING_ROLES))):
    require_case_staff(db, case_id)
    if len(access_reason.strip()) < 5:
        raise HTTPException(status_code=422, detail="A meaningful access reason is required.")
    notes = db.scalars(select(SafeguardingNote).where(
        SafeguardingNote.case_id == case_id).order_by(SafeguardingNote.created_at.desc())).all()
    audit(db, actor, "safeguarding_notes.viewed", "case", case_id, f"reason={access_reason[:300]}")
    db.commit()
    return [{"id": n.id, "author_id": n.author_id, "note_text": n.note_text,
             "created_at": n.created_at.isoformat()} for n in notes]

@app.get("/api/admin/audit")
def audit_log(db: Session = Depends(get_db),
              actor: User = Depends(require_roles(Role.administrator))):
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(200)).all()
    return [{"id": e.id, "actor_user_id": e.actor_user_id, "action": e.action,
             "object_type": e.object_type, "object_id": e.object_id,
             "occurred_at": e.occurred_at.isoformat(), "metadata_summary": e.metadata_summary} for e in events]

# Dashboard support endpoints. These return only the minimum fields needed by the UI.
@app.get("/api/admin/users", response_model=list[UserView])
def list_users(db: Session = Depends(get_db), actor: User = Depends(require_roles(Role.administrator, Role.staff))):
    return list(db.scalars(select(User).where(User.role == Role.client, User.is_active.is_(True)).order_by(User.full_name)).all())

@app.get("/api/admin/cases/{case_id}/workspace")
def case_workspace(case_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(*STAFF_ROLES))):
    case = require_case_staff(db, case_id)
    parties = db.scalars(select(CaseParty).where(CaseParty.case_id == case_id, CaseParty.is_active.is_(True))).all()
    docs = db.scalars(select(DocumentRecord).where(DocumentRecord.case_id == case_id).order_by(DocumentRecord.created_at.desc())).all()
    sessions = db.scalars(select(ContactSession).where(ContactSession.case_id == case_id).order_by(ContactSession.session_date, ContactSession.start_time)).all()
    audit(db, actor, "case.workspace_viewed", "case", case_id)
    db.commit()
    return {
        "case": {"id": case.id, "case_number": case.case_number, "case_title": case.case_title, "status": case.status},
        "parties": [{"membership_id": p.id, "user_id": p.user_id,
                     "name": (db.get(User, p.user_id).full_name if db.get(User, p.user_id) else "Unknown"),
                     "email": (db.get(User, p.user_id).email if db.get(User, p.user_id) else ""),
                     "party_type": p.party_type.value, "relationship_label": p.relationship_label,
                     "can_view_documents": p.can_view_documents, "can_view_schedule": p.can_view_schedule,
                     "can_submit_documents": p.can_submit_documents} for p in parties],
        "documents": [{"id": d.id, "filename": d.original_filename, "visibility": d.visibility.value,
                       "recipient_party_id": d.recipient_party_id, "uploaded_at": d.created_at.isoformat()} for d in docs],
        "sessions": [{"id": s.id, "date": s.session_date.isoformat(), "start_time": s.start_time.isoformat(),
                      "end_time": s.end_time.isoformat(), "venue": s.venue_label, "status": s.status} for s in sessions]
    }

@app.get("/api/admin/cases/{case_id}/documents/{document_id}/download")
def staff_download_document(case_id: int, document_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(*STAFF_ROLES))):
    record = db.get(DocumentRecord, document_id)
    if not record or record.case_id != case_id:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = Path(settings.private_upload_dir) / record.storage_key
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file not found.")
    audit(db, actor, "staff_document.downloaded", "document", record.id)
    db.commit()
    return FileResponse(path, media_type="application/pdf", filename=record.original_filename)

@app.post("/api/client/cases/{case_id}/documents")
async def client_upload_pdf(case_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_roles(Role.client))):
    _, party = client_case_or_404(db, case_id, user)
    if not party.can_submit_documents:
        raise HTTPException(status_code=403, detail="You are not authorized to submit documents for this case.")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Only PDF documents are accepted.")
    max_bytes = settings.max_pdf_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"PDF exceeds the {settings.max_pdf_mb} MB limit.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF.")
    key = f"{uuid4().hex}.pdf"
    (Path(settings.private_upload_dir) / key).write_bytes(content)
    record = DocumentRecord(case_id=case_id, uploaded_by_id=user.id, recipient_party_id=None,
                            original_filename=Path(file.filename or "client-upload.pdf").name[:255],
                            storage_key=key, size_bytes=len(content), visibility=DocumentVisibility.staff_only)
    db.add(record)
    db.flush()
    audit(db, user, "client_document.submitted", "document", record.id)
    db.commit()
    return {"id": record.id, "filename": record.original_filename, "message": "Your PDF has been securely submitted for staff review."}
