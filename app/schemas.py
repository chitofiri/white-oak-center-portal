from datetime import date, time
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from .models import Role, PartyType

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=180)
    password: str = Field(min_length=14, max_length=128)
    role: Role = Role.staff

class UserView(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

class CaseCreate(BaseModel):
    case_title: str = Field(min_length=2, max_length=180)

class CaseView(BaseModel):
    id: int
    case_number: str
    case_title: str
    status: str
    model_config = ConfigDict(from_attributes=True)

class CasePartyCreate(BaseModel):
    user_id: int
    party_type: PartyType
    relationship_label: str = Field(min_length=2, max_length=100)
    can_view_documents: bool = False
    can_view_schedule: bool = False
    can_submit_documents: bool = False

class ReferralCreate(BaseModel):
    form_data: dict = Field(description="Only approved referral fields; do not include unnecessary sensitive details.")

class ContactSessionCreate(BaseModel):
    session_date: date
    start_time: time
    end_time: time
    venue_label: str = Field(min_length=2, max_length=160)

class SafeguardingNoteCreate(BaseModel):
    note_text: str = Field(min_length=1, max_length=12000)
    access_reason: str = Field(min_length=5, max_length=500)
