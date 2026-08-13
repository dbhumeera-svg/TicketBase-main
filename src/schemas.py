import re
from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class TicketPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TicketCategory(str, Enum):
    HARDWARE = "HARDWARE"
    SOFTWARE = "SOFTWARE"
    NETWORK = "NETWORK"
    ACCESS = "ACCESS"
    OTHER = "OTHER"


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Role(str, Enum):
    ADMIN = "ADMIN"
    AGENT = "AGENT"
    USER = "USER"


class NotificationType(str, Enum):
    TICKET_CREATED = "TICKET_CREATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    COMMENT_ADDED = "COMMENT_ADDED"


_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Requires a digit, a lowercase letter, an uppercase letter and one of the
# listed special characters - mirrors the reference project's rule.
_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[0-9])(?=.*[a-z])(?=.*[A-Z])(?=.*[@#$%^&+=!]).*$"
)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str
    password: str = Field(min_length=8, max_length=100)
    # Admin is intentionally not accepted here - enforced in the route
    # handler, not just the type, so a bypass attempt gets a clear error
    # rather than silently falling through.
    role: Optional[Role] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not _USERNAME_PATTERN.match(value):
            raise ValueError(
                "Username may only contain letters, numbers, "
                "underscores, dots and hyphens."
            )
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not _EMAIL_PATTERN.match(value):
            raise ValueError("Invalid email address.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not _PASSWORD_PATTERN.match(value):
            raise ValueError(
                "Password must contain an uppercase letter, a lowercase "
                "letter, a digit, and one of @#$%^&+=! ."
            )
        return value


class LoginRequest(BaseModel):
    # Accepts either a username or an email in this one field, matching
    # the reference project's login behavior.
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: Role
    created_at: datetime


class AuthResponse(BaseModel):
    token: str
    token_type: str = "Bearer"
    user_id: int
    username: str
    email: str
    role: Role


class TicketCreate(BaseModel):
    title: str = Field(
        min_length=3,
        max_length=100,
    )

    description: str = Field(
        min_length=5,
        max_length=1000,
    )

    category: TicketCategory = (
        TicketCategory.OTHER
    )

    priority: TicketPriority = (
        TicketPriority.MEDIUM
    )


class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class TicketResponse(BaseModel):
    id: int
    ticket_number: str
    user_sequence: int
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    created_by: int
    created_by_username: str
    assigned_to: Optional[int]
    assigned_to_username: Optional[str]
    created_at: datetime
    updated_at: datetime


class PaginatedTickets(BaseModel):
    items: list[TicketResponse]
    page: int
    size: int
    total: int
    total_pages: int


class CommentCreate(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=1000,
    )


class CommentResponse(BaseModel):
    id: int
    ticket_id: int
    author_id: int
    author_username: str
    message: str
    created_at: datetime


class AttachmentPresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str


class AttachmentPresignResponse(BaseModel):
    attachment_id: int
    upload_url: str
    upload_fields: dict[str, str]


class AttachmentResponse(BaseModel):
    id: int
    ticket_id: int
    original_filename: str
    content_type: str
    size_bytes: Optional[int]
    created_at: datetime
    download_url: str
    thumbnail_url: str


class DashboardSummary(BaseModel):
    total_tickets: int
    by_status: dict[str, int]
    by_priority: dict[str, int]


class NotificationResponse(BaseModel):
    id: int
    ticket_id: Optional[int]
    type: NotificationType
    message: str
    is_read: bool
    created_at: datetime


class UnreadCountResponse(BaseModel):
    unread_count: int
