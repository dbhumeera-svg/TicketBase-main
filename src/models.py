from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from src.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # ADMIN / AGENT / USER - stored as plain text to match this project's
    # existing convention of storing enum values as strings (see
    # Ticket.category/priority/status) rather than a DB-level enum type.
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="USER",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    tickets_created: Mapped[list["Ticket"]] = (
        relationship(
            back_populates="creator",
            foreign_keys="Ticket.created_by_id",
        )
    )

    tickets_assigned: Mapped[list["Ticket"]] = (
        relationship(
            back_populates="assignee",
            foreign_keys="Ticket.assigned_to_id",
        )
    )


class Ticket(Base):

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # Human-facing identifier (e.g. "TKT-4821-01") plus the creator's
    # per-user ticket sequence number, mirroring the reference project.
    ticket_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    user_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OTHER",
    )

    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MEDIUM",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="OPEN",
    )

    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    assigned_to_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    creator: Mapped["User"] = relationship(
        back_populates="tickets_created",
        foreign_keys=[created_by_id],
    )

    assignee: Mapped[Optional["User"]] = relationship(
        back_populates="tickets_assigned",
        foreign_keys=[assigned_to_id],
    )

    comments: Mapped[list["Comment"]] = (
        relationship(
            back_populates="ticket",
            cascade="all, delete-orphan",
        )
    )

    attachment: Mapped[Optional["Attachment"]] = (
        relationship(
            back_populates="ticket",
            cascade="all, delete-orphan",
            uselist=False,
        )
    )

    notifications: Mapped[list["Notification"]] = (
        relationship(
            back_populates="ticket",
            cascade="all, delete-orphan",
        )
    )


class Comment(Base):

    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    ticket_id: Mapped[int] = mapped_column(
        ForeignKey(
            "tickets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    ticket: Mapped["Ticket"] = relationship(
        back_populates="comments"
    )

    author: Mapped["User"] = relationship()


class Attachment(Base):

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    ticket_id: Mapped[int] = mapped_column(
        ForeignKey(
            "tickets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Key of the *original* upload under the attachments bucket, e.g.
    # attachments/{ticket_id}/{uuid}-{filename}. The browser PUTs the
    # bytes straight to S3 via a presigned POST - the API never touches
    # them (checklist item 23). The Lambda thumbnailer writes its output
    # to the same bucket under thumbnails/, derived from this key.
    s3_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        unique=True,
    )

    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Unknown until the browser finishes the direct-to-S3 upload, which
    # the API is never told about - so this stays null until/unless
    # something reconciles it. Not required for the app to function.
    size_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    ticket: Mapped["Ticket"] = relationship(
        back_populates="attachment"
    )


class Notification(Base):

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    recipient_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    ticket_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "tickets.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    # TICKET_CREATED / STATUS_CHANGED / COMMENT_ADDED
    type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    recipient: Mapped["User"] = relationship()

    ticket: Mapped[Optional["Ticket"]] = relationship(
        back_populates="notifications"
    )
