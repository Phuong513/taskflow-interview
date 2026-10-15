# app/routers/auth.py

import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

password_context = CryptContext(
    schemes=["bcrypt", "bcrypt_sha256", "hex_md5"],
    deprecated=["hex_md5"],
    bcrypt__rounds=12,
    bcrypt__truncate_error=True,
    bcrypt_sha256__rounds=12,
)


def hash_password(password: str) -> str:
    # Plain bcrypt cannot represent NUL or more than 72 UTF-8 bytes safely.
    scheme = (
        "bcrypt_sha256"
        if "\x00" in password or len(password.encode("utf-8")) > 72
        else "bcrypt"
    )
    return password_context.hash(password, scheme=scheme)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        scheme = password_context.identify(hashed_password)
        # truncate_error protects hash(), but bcrypt verification also truncates.
        if scheme == "bcrypt" and (
            "\x00" in plain_password or len(plain_password.encode("utf-8")) > 72
        ):
            return False
        return password_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        # Unknown or malformed stored credentials must fail authentication.
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _credential_version(user_id: int, password_hash: str) -> str:
    # Bind tokens to this credential record without exposing its password hash.
    return hmac.new(
        SECRET_KEY.encode("utf-8"),
        f"{user_id}:{password_hash}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    version = payload.get("ver")
    if not isinstance(version, str) or not hmac.compare_digest(
        version.encode("utf-8"),
        _credential_version(user.id, user.password_hash).encode("ascii"),
    ):
        raise credentials_exception
    return user


def get_current_active_user(current_user=Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# Issue: No rate limiting on the login endpoint — vulnerable to brute force
@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(
        models.User.username == form_data.username
    ).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    credential_hash = user.password_hash
    if password_context.needs_update(user.password_hash):
        # Legacy MD5 records are upgraded only after a successful verification.
        user_id = user.id
        original_hash = user.password_hash
        upgraded_hash = hash_password(form_data.password)
        updated = db.query(models.User).filter(
            models.User.id == user_id,
            models.User.password_hash == original_hash,
        ).update({models.User.password_hash: upgraded_hash}, synchronize_session=False)
        db.commit()
        credential_hash = upgraded_hash
        if not updated:
            # A concurrent password change must not be overwritten or bypassed.
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if not user or not verify_password(form_data.password, user.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect username or password",
                )
            credential_hash = user.password_hash

    token = create_access_token(
        data={"sub": str(user.id), "ver": _credential_version(user.id, credential_hash)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/register", response_model=schemas.UserOut, status_code=200)
# Issue: should return 201 Created, not 200
def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(
        models.User.email == user_data.email
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Issue: no check for duplicate username
    new_user = models.User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
