"""Request/response schemas for authentication."""

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    # Either create a new household (household_name) or join one (invite_code).
    household_name: str | None = Field(default=None, max_length=120)
    invite_code: str | None = Field(default=None, max_length=64)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    household_id: int

    model_config = {"from_attributes": True}


class HouseholdOut(BaseModel):
    id: int
    name: str
    invite_code: str
    members: list[UserOut]

    model_config = {"from_attributes": True}


class MeOut(BaseModel):
    user: UserOut
    household: HouseholdOut
