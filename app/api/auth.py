# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
import bcrypt
from jose import JWTError, jwt

from app.config import settings
from app.database import get_db
from app.models.schemas import Team, User

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": str(user_id), "exp": exp}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return int(payload.get("sub"))
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    user_id = decode_token(creds.credentials)
    user = db.query(User).filter(User.id == user_id, User.status == "active").first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_role(roles: list):
    def checker(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user
    return checker


class RegisterBody(BaseModel):
    team_name: str
    email: EmailStr
    password: str
    name: str = ""


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: Optional[str]
    role: str
    team_id: Optional[int]

    class Config:
        from_attributes = True


class TeamOut(BaseModel):
    id: int
    name: str
    plan: str

    class Config:
        from_attributes = True


@router.post("/register")
def register(body: RegisterBody, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    team = Team(name=body.team_name, plan="trial", max_members=1)
    db.add(team)
    db.flush()

    user = User(
        team_id=team.id,
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name or body.email.split("@")[0],
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    return {"token": token, "user": UserOut.model_validate(user), "team": TeamOut.model_validate(team)}


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.status == "active").first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user.id)
    team = db.query(Team).filter(Team.id == user.team_id).first() if user.team_id else None
    return {"token": token, "user": UserOut.model_validate(user), "team": TeamOut.model_validate(team) if team else None}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == user.team_id).first() if user.team_id else None
    return {"user": UserOut.model_validate(user), "team": TeamOut.model_validate(team) if team else None}
