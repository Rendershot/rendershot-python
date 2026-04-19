"""
Webhook receiver utilities.

Rendershot signs every outbound webhook POST with an HMAC-SHA256 over
``"{timestamp}.{body}"`` using the per-endpoint secret shown on the
Webhooks dashboard page. Use :func:`verify_signature` in your receiver
to reject forged or replayed requests before acting on them.

The API itself is server-side — this module lives in the SDK only to
save every user from re-implementing the HMAC verify themselves.
"""

from __future__ import annotations

import hashlib
import hmac
import time

SIGNATURE_HEADER = 'X-Rendershot-Signature'
TIMESTAMP_HEADER = 'X-Rendershot-Timestamp'
EVENT_HEADER = 'X-Rendershot-Event'
DELIVERY_HEADER = 'X-Rendershot-Delivery'

DEFAULT_MAX_AGE_SECONDS = 300


class WebhookVerificationError(Exception):
    """Raised by :func:`verify_signature` when strict verification fails.

    The non-strict entry point (:func:`is_valid_signature`) returns ``False``
    instead of raising, which is easier to wire into a web framework's
    middleware.
    """


def _compute_signature(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), msg=f'{timestamp}.'.encode() + body, digestmod=hashlib.sha256)
    return f'sha256={mac.hexdigest()}'


def is_valid_signature(
    secret: str,
    body: bytes | str,
    signature_header: str,
    timestamp_header: str,
    *,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    now: float | None = None,
) -> bool:
    """Return ``True`` iff the HMAC signature matches and is within age.

    Does not raise — intended for "if not ok: return 400" flows. Use
    :func:`verify_signature` if you want a raise-on-failure variant.
    """
    if isinstance(body, str):
        body = body.encode()

    # Reject obviously-malformed inputs (empty strings, missing headers).
    if not signature_header or not timestamp_header:
        return False

    try:
        ts = int(timestamp_header)
    except (TypeError, ValueError):
        return False

    current = now if now is not None else time.time()
    if abs(current - ts) > max_age_seconds:
        return False

    expected = _compute_signature(secret, timestamp_header, body)
    return hmac.compare_digest(expected, signature_header)


def verify_signature(
    secret: str,
    body: bytes | str,
    signature_header: str,
    timestamp_header: str,
    *,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    now: float | None = None,
) -> None:
    """Raise :class:`WebhookVerificationError` on any failure.

    Use when you'd rather let an exception bubble up than branch on a bool.
    """
    if not is_valid_signature(
        secret,
        body,
        signature_header,
        timestamp_header,
        max_age_seconds=max_age_seconds,
        now=now,
    ):
        raise WebhookVerificationError('webhook signature verification failed')
