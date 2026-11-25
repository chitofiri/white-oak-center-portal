# White Oak Center Client Portal — Milestone 3 Development Build

This project is a development build for White Oak Center's supervised child and family contact service. It contains a staff workspace and a client portal connected to the FastAPI backend.

## Important safety and deployment status

**This is not production-ready and is not certified as UK GDPR, Data Protection Act 2018, HIPAA or any other compliance standard. Do not use real client, child, court, health, safeguarding or confidential information. Use fictional test data only.**

Before live use, White Oak Center needs qualified UK data-protection/legal and safeguarding review, a DPIA, data-flow mapping, documented lawful bases and any applicable Article 9/Article 10 conditions, privacy notices, retention and deletion rules, processor contracts, incident response, a role/access matrix, and security testing. HIPAA applicability must be assessed separately; the organisation being UK-based does not itself make HIPAA applicable.

## Included in Milestone 3

- Responsive White Oak Center login and role-specific dashboards.
- FastAPI backend, SQLAlchemy models and PostgreSQL-ready configuration.
- Roles: administrator, staff, safeguarding lead and client.
- Password hashing, JWT authentication and role checks.
- Administrators and staff can create client accounts; staff can create client accounts only. Only administrators can create staff/safeguarding-lead accounts.
- Staff case register, case creation and case workspace.
- Explicit case membership grants with separate permissions for document viewing, schedule viewing and submissions.
- Staff can grant/revoke client access for an individual case.
- Staff can create contact sessions and see the case schedule.
- Staff can upload PDFs; documents default to staff-only and can be shared with one explicitly authorized case membership.
- Clients can see only assigned cases and only documents/schedules allowed by their membership permissions.
- Clients can submit PDFs where submission permission is granted.
- A basic referral submission text field, saved against the assigned case. It must be replaced with White Oak Center's approved referral form fields before live use.
- Restricted safeguarding notes for administrators and safeguarding leads, with a reason required to view notes and audit events recorded.
- Administrator audit activity view.
- PDF size/type/signature checks; development uploads are stored on local disk.

## Not yet implemented / production blockers

- Email delivery, email templates, delivery logs, and automatic client notifications.
- Secure production identity provider, MFA, secure HttpOnly cookie sessions, CSRF protection and robust session revocation. The development UI currently keeps its bearer token in `sessionStorage`.
- Private UK-region object storage, encryption/key-management configuration, malware scanning and content disarm/reconstruction.
- Production database migrations, transaction-safe case-number allocation and concurrency testing.
- Complete case status workflow, requested-document workflow, availability management, scheduling conflict detection, cancellation/rescheduling and calendar integration.
- Final approved referral form, configurable document templates, client acknowledgements and staff review/approval workflow.
- Granular access matrix for children, parents, guardians, representatives, solicitors and social workers; professional review of what each party may see.
- Safeguarding break-glass access, immutable/tamper-evident audit storage, retention/deletion automation, legal holds and data-subject rights workflows.
- Penetration testing, dependency/security review, backup restore testing, DPIA and independent compliance assessment.

## Run locally (fictional data only)

1. Install Python 3.11+ and PostgreSQL 15+.
2. Copy `.env.example` to `.env`; set a strong unique `JWT_SECRET`, database URL and bootstrap administrator details.
3. Create the PostgreSQL database.
4. Install dependencies:

   ```bash
   python -m venv .venv
   # Windows:
   .venv\\Scripts\\activate
   # macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

5. Create the first administrator:

   ```bash
   python -m app.bootstrap_admin
   ```

6. Start the API:

   ```bash
   uvicorn app.main:app --reload
   ```

7. Open `http://127.0.0.1:8000`. Development API documentation is at `http://127.0.0.1:8000/docs` when `ENVIRONMENT=development`.

There is no hard-coded administrator or default password. Remove bootstrap credentials from the environment after creating the first administrator. Do not expose the bootstrap process in production.


## Deploy to Railway (initial hosting)

This project includes a Railway configuration (`railway.toml`). Deploy the **contents of this project folder** as the service root (the folder containing `requirements.txt`, `railway.toml`, `app/` and `web/`).

1. Push this folder to a private GitHub repository. Do not commit `.env`, passwords, JWT secrets, real client information or uploaded documents.
2. In Railway, create a project and deploy the GitHub repository as a service. If the repository contains this project inside a subfolder, set that subfolder as the service Root Directory.
3. Add a Railway PostgreSQL service. In the web service variables, set `DATABASE_URL` to the PostgreSQL service reference, normally `${{Postgres.DATABASE_URL}}` (use the exact service name shown in your project). The app normalizes Railway's common `postgres://` / `postgresql://` URL forms for psycopg 3.
4. Add these web-service variables:
   - `ENVIRONMENT=production`
   - `JWT_SECRET` = a newly generated, long random secret (at least 32 bytes)
   - `ACCESS_TOKEN_MINUTES=20`
   - `MAX_PDF_MB=15`
   - `PRIVATE_UPLOAD_DIR=/data/private_uploads`
   - `BOOTSTRAP_ADMIN_EMAIL` = the intended administrator email
   - `BOOTSTRAP_ADMIN_PASSWORD` = a unique password of at least 14 characters
5. Add a Railway Volume to the **web service**, mounted at `/data`. This is needed for uploaded PDFs to persist across redeploys. Keep the volume private; do not expose it as a public static directory.
6. Deploy. Railway uses `railway.toml` to start Uvicorn and check `/api/health`.
7. Create the first administrator once, using Railway's service shell / one-off command: `python -m app.bootstrap_admin`. Confirm the account works, then remove `BOOTSTRAP_ADMIN_PASSWORD` (and preferably the bootstrap email variable) from the service variables and redeploy. Do not leave bootstrap credentials configured.
8. Test login, case access, document upload/download, permission revocation and database persistence using fictional test records only.

### Railway deployment limitations

Railway is being used here as an initial hosting platform, not as a declaration of UK GDPR compliance. Choose and verify the data region and contractual terms before any real personal data is entered. The app currently stores PDFs on a mounted Railway volume; this is not a substitute for a reviewed private object-storage design, malware scanning, key management, retention controls and tested backups. Back up the database and volume independently and test restoration.

The current application still creates database tables at startup and uses a development-style case-number allocator. Before production use, replace startup table creation with reviewed Alembic migrations, implement a concurrency-safe case-number allocator, complete security testing and the approved safeguarding/access policy, and replace the current browser token storage with an approved production session design. Email notifications are not yet integrated. **Do not upload real children's records, court documents or safeguarding information to this milestone.**

## Access behaviour

- A client sees only cases with an active membership grant for that exact user account.
- Document, schedule and submission permissions are independently configurable for each membership.
- Uploaded PDFs are private by default. Staff must deliberately share a PDF with one active membership; it is not automatically visible to other parties on the case.
- Revoking a membership removes the account's ability to use the client case/document/schedule endpoints for that grant.
- Safeguarding notes are not part of the ordinary case document list. Only administrators and safeguarding leads can create/read them, and reading requires an access reason.
- The current case-party model is only a starting point. It does not decide whether a parent, guardian, child representative, solicitor or social worker should legally or safely receive information. White Oak Center must approve that access matrix before any real use.

## Technical notes

- Tables are currently created at application startup for development. Replace this with reviewed Alembic migrations before production.
- Case numbers are generated using a development-only count-based allocator. Replace with a database sequence or transaction-safe allocator before production.
- Local file storage is for development only. A production deployment needs private object storage in an approved UK region, restricted service access, encryption/key management, malware scanning, backups and tested restore procedures.
- The UI is a working milestone interface, not a final approved workflow. Email notifications and logs are not connected to an email provider yet.
