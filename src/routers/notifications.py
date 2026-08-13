from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import Notification, User
from src.schemas import NotificationResponse, UnreadCountResponse
from src.security import get_current_user


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=List[NotificationResponse],
)
def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    return (
        db.query(Notification)
        .filter(Notification.recipient_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
)
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    count = (
        db.query(Notification)
        .filter(
            Notification.recipient_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .count()
    )

    return UnreadCountResponse(unread_count=count)


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    notification = db.get(Notification, notification_id)

    if (
        notification is None
        or notification.recipient_id != current_user.id
    ):

        raise HTTPException(
            status_code=404,
            detail="Notification not found",
        )

    notification.is_read = True

    db.commit()

    db.refresh(notification)

    return notification


@router.patch("/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    (
        db.query(Notification)
        .filter(
            Notification.recipient_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .update({"is_read": True})
    )

    db.commit()

    return {"message": "All notifications marked as read"}
