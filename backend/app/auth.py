import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .agent import verify_credential
from .config import COOKIE_NAME, COOKIE_SECURE, SESSION_DAYS, fernet
from .db import AuthSession, User, get_session, now

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def token_kind(token: str) -> str:
    if token.startswith("sk-ant-oat"):
        return "oauth"
    if token.startswith("sk-ant-api"):
        return "api_key"
    raise HTTPException(400, "That doesn't look like a Claude token. Run `claude setup-token` and "
                             "paste the sk-ant-oat… value it prints.")


class LoginIn(BaseModel):
    token: str = Field(min_length=20, max_length=500)
    name: str = Field(default="", max_length=80)


class UserOut(BaseModel):
    id: str
    name: str
    token_kind: str
    token_hint: str


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, name=user.name, token_kind=user.token_kind, token_hint=user.token_hint)


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, response: Response, db: Session = Depends(get_session)):
    token = body.token.strip()
    kind = token_kind(token)
    # One workspace per Claude credential: signing in again with the same token lands
    # in the same workspace.
    user_id = "usr_" + _sha("picasso-user:" + token)[:20]
    try:
        await verify_credential(token, kind, user_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, f"Claude didn't accept that token: {exc}") from exc

    user = db.get(User, user_id)
    if not user:
        user = User(id=user_id, name=body.name.strip() or "My workspace", token_kind=kind,
                    token_enc="", token_hint="")
    elif body.name.strip():
        user.name = body.name.strip()
    user.token_kind = kind
    user.token_enc = fernet.encrypt(token.encode()).decode()
    user.token_hint = f"{token[:10]}…{token[-4:]}"
    db.add(user)

    raw = secrets.token_urlsafe(32)
    db.add(AuthSession(id=_sha(raw), user_id=user.id, expires_at=now() + timedelta(days=SESSION_DAYS)))
    db.commit()
    db.refresh(user)
    response.set_cookie(COOKIE_NAME, raw, max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=COOKIE_SECURE, path="/")
    return user_out(user)


def current_user(
    picasso_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_session),
) -> User:
    if not picasso_session:
        raise HTTPException(401, "Not signed in")
    session = db.get(AuthSession, _sha(picasso_session))
    if not session or session.expires_at.replace(tzinfo=now().tzinfo) < now():
        raise HTTPException(401, "Session expired")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, "Not signed in")
    return user


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_session)):
    user.name = body.name.strip()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.post("/logout")
def logout(response: Response,
           picasso_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
           db: Session = Depends(get_session)):
    if picasso_session:
        session = db.get(AuthSession, _sha(picasso_session))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/forget")
def forget(response: Response, user: User = Depends(current_user), db: Session = Depends(get_session)):
    """Sign out everywhere and drop the stored Claude token."""
    for session in db.exec(select(AuthSession).where(AuthSession.user_id == user.id)).all():
        db.delete(session)
    user.token_enc = ""
    user.token_hint = ""
    db.add(user)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}
