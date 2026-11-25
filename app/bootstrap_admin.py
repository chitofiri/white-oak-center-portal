from sqlalchemy import select
from .config import settings
from .database import Base, engine, SessionLocal
from .models import User, Role
from .security import hash_password

def main():
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        raise SystemExit("Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD in .env first.")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        email = settings.bootstrap_admin_email.lower()
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("That administrator account already exists.")
        user = User(email=email, full_name="White Oak Administrator",
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role=Role.administrator)
        db.add(user)
        db.commit()
        print("Initial administrator created. Remove bootstrap credentials from .env now.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
