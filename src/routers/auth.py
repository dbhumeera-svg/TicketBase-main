from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import User
from src.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    Role,
    UserResponse,
)
from src.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):

    if payload.role == Role.ADMIN:

        raise HTTPException(
            status_code=400,
            detail=(
                "Admin accounts cannot be self-registered. Admin users "
                "are provisioned internally."
            ),
        )

    if db.query(User).filter(
        User.username == payload.username
    ).one_or_none():

        raise HTTPException(
            status_code=409,
            detail=(
                f"Username '{payload.username}' is already taken."
            ),
        )

    if db.query(User).filter(
        User.email == payload.email
    ).one_or_none():

        raise HTTPException(
            status_code=409,
            detail=(
                f"Email '{payload.email}' is already registered."
            ),
        )

    # Anything other than an explicit AGENT request collapses to a plain
    # USER account - ADMIN was already rejected above.
    role = (
        Role.AGENT.value
        if payload.role == Role.AGENT
        else Role.USER.value
    )

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=role,
    )

    db.add(user)

    db.commit()

    db.refresh(user)

    return user


@router.post(
    "/login",
    response_model=AuthResponse,
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):

    user = (
        db.query(User)
        .filter(
            (User.username == payload.username)
            | (User.email == payload.username)
        )
        .one_or_none()
    )

    if user is None or not verify_password(
        payload.password, user.password_hash
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    token = create_access_token(user)

    return AuthResponse(
        token=token,
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
):

    return current_user


@router.get(
    "/agents",
    response_model=list[UserResponse],
)
def get_agents(
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(Role.ADMIN, Role.AGENT)
    ),
):

    return (
        db.query(User)
        .filter(User.role == Role.AGENT.value)
        .order_by(User.username)
        .all()
    )
