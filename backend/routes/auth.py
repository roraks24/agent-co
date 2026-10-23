"""
Authentication routes for User Registration, Login, and Session resolution.

Rorak AI V2.6: Authentication & Multi-User Isolation.
"""
import logging
import re
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.core.auth import get_current_user
from backend.core.config import ACCESS_TOKEN_EXPIRE_MINUTES
from backend.core.database import get_db
from backend.core.security import create_access_token, hash_password, verify_password
from backend.models.db import User
from backend.models.schemas import (
    APIErrorResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from backend.repositories.user_repository import UserRepository


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        409: {"model": APIErrorResponse, "description": "Duplicate User Conflict"},
        422: {"model": APIErrorResponse, "description": "Validation Error"},
    },
)
def register_user(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Register a new user account with password hashing, email validation,
    and duplicate-user prevention.
    """
    clean_email = payload.email.strip().lower()

    # Email format validation
    if not clean_email or not EMAIL_REGEX.match(clean_email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": "Invalid email address format."}},
        )

    # Password validation
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": "Password must be at least 8 characters long."}},
        )

    repo = UserRepository(db)
    existing_user = repo.get_by_email(clean_email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "DUPLICATE_EMAIL", "message": "A user with this email address already exists."}},
        )

    clean_name = payload.name.strip() if payload.name and payload.name.strip() else None

    hashed = hash_password(payload.password)
    user = User(
        id=uuid4(),
        email=clean_email,
        name=clean_name,
        password_hash=hashed,
    )
    repo.create(user)

    if clean_name:
        try:
            from backend.repositories.memory_repository import MemoryRepository
            from backend.models.db.memory import Memory
            mem_repo = MemoryRepository(db)
            mem_repo.create(
                Memory(
                    id=uuid4(),
                    user_id=user.id,
                    content=f"User's name is {clean_name}",
                    memory_type="user_preference",
                )
            )
        except Exception as e:
            logger.warning("Could not auto-create memory for user name: %s", e)

    db.commit()
    db.refresh(user)

    logger.info("Successfully registered new user: %s (ID: %s, Name: %s)", user.email, user.id, user.name)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": APIErrorResponse, "description": "Invalid Credentials"},
    },
)
def login_user(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Authenticate user with email and password, returning a signed JWT access token.
    """
    clean_email = payload.email.strip().lower()
    repo = UserRepository(db)
    user = repo.get_by_email(clean_email)

    if (
        user is None
        or not user.password_hash
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )

    expires_in = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    logger.info("User %s authenticated successfully.", user.email)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
    },
)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve authenticated user profile resolved from JWT Bearer token.
    """
    return current_user
