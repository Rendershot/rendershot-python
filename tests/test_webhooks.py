"""Webhook signature verification helpers."""

from __future__ import annotations

import hashlib
import hmac

import pytest

import rendershot

SECRET = 'supersecret'
BODY = b'{"event":"job.completed","job_id":"abc"}'


def _make_sig(ts: str, body: bytes, secret: str = SECRET) -> str:
    mac = hmac.new(secret.encode(), msg=f'{ts}.'.encode() + body, digestmod=hashlib.sha256)
    return f'sha256={mac.hexdigest()}'


class TestIsValidSignature:
    def test_accepts_matching_signature(self) -> None:
        ts = '1776540000'
        sig = _make_sig(ts, BODY)
        # Pin `now` so the age-window check can't race.
        assert rendershot.is_valid_signature(SECRET, BODY, sig, ts, now=float(ts) + 1)

    def test_rejects_tampered_body(self) -> None:
        ts = '1776540000'
        sig = _make_sig(ts, BODY)
        assert not rendershot.is_valid_signature(SECRET, b'tampered', sig, ts, now=float(ts) + 1)

    def test_rejects_wrong_secret(self) -> None:
        ts = '1776540000'
        sig = _make_sig(ts, BODY, secret='other')
        assert not rendershot.is_valid_signature(SECRET, BODY, sig, ts, now=float(ts) + 1)

    def test_rejects_stale_timestamp(self) -> None:
        ts = '1776540000'
        sig = _make_sig(ts, BODY)
        # 10 minutes after the signed timestamp — past the 5-minute default.
        assert not rendershot.is_valid_signature(SECRET, BODY, sig, ts, now=float(ts) + 600)

    def test_rejects_future_timestamp(self) -> None:
        ts = '1776540000'
        sig = _make_sig(ts, BODY)
        # Clock-skew guard works in both directions.
        assert not rendershot.is_valid_signature(SECRET, BODY, sig, ts, now=float(ts) - 600)

    def test_rejects_missing_signature(self) -> None:
        ts = '1776540000'
        assert not rendershot.is_valid_signature(SECRET, BODY, '', ts, now=float(ts))

    def test_rejects_missing_timestamp(self) -> None:
        ts = '1776540000'
        sig = _make_sig(ts, BODY)
        assert not rendershot.is_valid_signature(SECRET, BODY, sig, '', now=float(ts))

    def test_rejects_non_numeric_timestamp(self) -> None:
        sig = _make_sig('1776540000', BODY)
        assert not rendershot.is_valid_signature(SECRET, BODY, sig, 'not-a-number', now=1776540000.0)

    def test_accepts_str_body(self) -> None:
        ts = '1776540000'
        text = '{"ok":true}'
        sig = _make_sig(ts, text.encode())
        assert rendershot.is_valid_signature(SECRET, text, sig, ts, now=float(ts) + 1)


class TestVerifySignature:
    def test_returns_none_on_success(self) -> None:
        ts = '1776540000'
        sig = _make_sig(ts, BODY)
        assert rendershot.verify_signature(SECRET, BODY, sig, ts, now=float(ts) + 1) is None

    def test_raises_on_failure(self) -> None:
        ts = '1776540000'
        with pytest.raises(rendershot.WebhookVerificationError):
            rendershot.verify_signature(SECRET, BODY, 'sha256=deadbeef', ts, now=float(ts) + 1)
