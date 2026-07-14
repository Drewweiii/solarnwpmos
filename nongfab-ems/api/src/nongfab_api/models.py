from datetime import datetime

from sqlalchemy import TIMESTAMP, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserORM(Base):
    """Maps to the `users` table created by db/migrations/0004_users.sql.

    Passwords are stored as bcrypt hashes (auth.py), never plaintext. `role`
    is one of admin/operator/viewer (RBAC.ROLE_HIERARCHY in auth.py defines
    what each role can do) - enforced by a CHECK constraint in the migration,
    not re-validated here (ORM trusts the DB schema it maps).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    hashed_password: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
