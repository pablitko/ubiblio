"""API tokens: random bearer tokens, stored only as SHA-256 hashes."""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import models

SCOPES = ("read", "write")
PREFIX = "ubt_"


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(db: Session, name: str, scope: str, user_id: int) -> tuple[models.apiToken, str]:
    """Create a token and return (row, plaintext). The plaintext is not stored anywhere."""
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}")
    token = PREFIX + secrets.token_urlsafe(32)
    row = models.apiToken(name=name.strip() or "token", tokenHash=hash_token(token), scope=scope, userId=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, token


def find_token(db: Session, token: str) -> models.apiToken | None:
    """Active token row for a presented token, or None. Updates lastUsedAt."""
    if not token or not token.startswith(PREFIX):
        return None
    digest = hash_token(token)
    row = db.query(models.apiToken).filter(models.apiToken.tokenHash == digest).first()
    if row is None or not hmac.compare_digest(row.tokenHash, digest) or row.revokedAt is not None:
        return None
    row.lastUsedAt = _now()
    db.commit()
    return row


def allows(row: models.apiToken, scope: str) -> bool:
    """A write token can also read."""
    return row.scope == scope or row.scope == "write"


def list_tokens(db: Session):
    return db.query(models.apiToken).order_by(models.apiToken.id.desc()).all()


def revoke_token(db: Session, token_id: int) -> bool:
    row = db.get(models.apiToken, token_id)
    if row is None:
        return False
    if row.revokedAt is None:
        row.revokedAt = _now()
        db.commit()
    return True
