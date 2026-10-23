"""User persistence repository."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.db.models.user import User


class UserRepository:
    """Repository handling User CRUD operations."""

    @staticmethod
    def get_by_id(db: Session, user_id: UUID) -> Optional[User]:
        return db.get(User, user_id)

    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email.lower().strip())
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def create(
        db: Session,
        email: str,
        name: Optional[str] = None,
        password_hash: Optional[str] = None,
    ) -> User:
        user = User(
            email=email.lower().strip(),
            name=name,
            password_hash=password_hash,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_or_create(
        db: Session,
        email: str,
        name: Optional[str] = None,
    ) -> User:
        user = UserRepository.get_by_email(db, email)
        if user is None:
            user = UserRepository.create(db, email=email, name=name)
        return user

    @staticmethod
    def list_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
        stmt = select(User).offset(skip).limit(limit)
        return list(db.execute(stmt).scalars().all())
