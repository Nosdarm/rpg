from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Union, Dict, List # Added Dict

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ValidationError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.database import get_async_session # For FastAPI Depends
from src.models.master_user import MasterUser # For FastAPI Depends
from src.core.crud import crud_master_user # For FastAPI Depends

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

class TokenPayload(BaseModel):
    sub: str  # MasterUser ID
    discord_user_id: Optional[str] = None
    active_guild_id: Optional[str] = None
    accessible_guilds: Optional[List[Dict[str, str]]] = None # Список словарей: [{"id": "guild_id", "name": "guild_name"}]
    # 'exp' is handled by jose library

def create_access_token(subject_data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    if not settings.SECRET_KEY:
        raise ValueError("SECRET_KEY is not configured. Cannot create JWT.")
    if "sub" not in subject_data:
        raise ValueError("Subject data for JWT must contain a 'sub' field (MasterUser ID).")

    to_encode = subject_data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode["exp"] = expire

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token_payload(token: str) -> Optional[TokenPayload]:
    """
    Verifies the JWT token and returns its payload as TokenPayload.
    Returns None if the token is invalid, expired, or does not match TokenPayload schema.
    """
    if not settings.SECRET_KEY:
        # Log this critical configuration error
        # logger.critical("SECRET_KEY is not configured. Cannot verify JWT.")
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)
        return token_data
    except (JWTError, ValidationError):
        return None

# --- FastAPI Dependencies ---

# tokenUrl points to the endpoint where the client *obtains* the token.
# For Discord OAuth2, this is our /api/auth/discord/callback.
# auto_error=False means if the token is missing, Depends(oauth2_scheme) will return None,
# rather than raising an HTTPException automatically. We'll check for None in get_current_token_payload.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/discord/callback", auto_error=False)

async def get_current_token_payload(token: Optional[str] = Depends(oauth2_scheme)) -> TokenPayload:
    """
    FastAPI dependency to get and validate JWT from Authorization header.
    Returns TokenPayload or raises HTTPException on error or missing token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token expired/missing",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None: # If token was not provided
        raise credentials_exception

    token_payload = verify_token_payload(token)
    if token_payload is None:
        raise credentials_exception
    return token_payload

async def get_current_master_user(
    session: AsyncSession = Depends(get_async_session),
    token_payload: TokenPayload = Depends(get_current_token_payload)
) -> MasterUser:
    """
    FastAPI dependency to get the current authenticated MasterUser from DB
    based on 'sub' from a valid JWT.
    """
    if token_payload.sub is None: # Should be validated by TokenPayload model, but good to check
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, # Or 400 Bad Request as token is malformed
            detail="Invalid token: subject (user ID) missing.",
        )
    try:
        user_id = int(token_payload.sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: subject (user ID) is not a valid integer.",
        )

    user = await crud_master_user.get(session, id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MasterUser not found for token subject.")
    return user

# (Optional) Password hashing functions (not used for Discord OAuth2)
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
