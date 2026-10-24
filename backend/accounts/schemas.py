from datetime import datetime
from typing import Literal

from ninja import Schema
from pydantic import Field

from core.domain import Role

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class MeOut(Schema):
    id: int
    email: str
    display_name: str
    roles: list[Role] = Field(description="Roles as granted.")
    effective_roles: list[Role] = Field(description="Granted roles plus implied ones (a lead is also a reviewer).")
    is_available: bool


class MeUpdateIn(Schema):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    is_available: bool | None = None


class UserOut(Schema):
    """A person as shown in pickers (assignee, @mention) and the admin user list."""

    id: int
    email: str
    display_name: str
    roles: list[Role]
    is_available: bool
    is_active: bool


class UserCreateIn(Schema):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    roles: list[Role] = Field(min_length=1)
    password: str = Field(min_length=12)


class UserUpdateIn(Schema):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    roles: list[Role] | None = Field(default=None, min_length=1)
    is_active: bool | None = None
    is_available: bool | None = None


class DemoResetOut(Schema):
    """A Reset demo job. `seeded_items` is set once it's done; `error` says what happened if it failed."""

    id: int
    status: Literal["queued", "running", "done", "failed"]
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    seeded_items: int
    error: str
