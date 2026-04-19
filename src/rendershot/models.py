from __future__ import annotations

import datetime
import enum

import pydantic


class ScreenshotFormat(enum.StrEnum):
    png = 'png'
    jpeg = 'jpeg'


class PDFFormat(enum.StrEnum):
    A3 = 'A3'
    A4 = 'A4'
    Letter = 'Letter'
    Legal = 'Legal'


class PDFOrientation(enum.StrEnum):
    portrait = 'portrait'
    landscape = 'landscape'


class AICleanupMode(enum.StrEnum):
    fast = 'fast'
    thorough = 'thorough'


class ViewportParams(pydantic.BaseModel):
    width: int = pydantic.Field(default=1280, ge=1, le=3840)
    height: int = pydantic.Field(default=720, ge=1, le=2160)
    device_scale_factor: float = pydantic.Field(default=1.0, ge=0.5, le=3.0)


class ClipParams(pydantic.BaseModel):
    x: int = pydantic.Field(ge=0)
    y: int = pydantic.Field(ge=0)
    width: int = pydantic.Field(ge=1)
    height: int = pydantic.Field(ge=1)


class MarginParams(pydantic.BaseModel):
    top: str = '1cm'
    right: str = '1cm'
    bottom: str = '1cm'
    left: str = '1cm'


class SameSite(enum.StrEnum):
    lax = 'Lax'
    strict = 'Strict'
    none = 'None'


class Cookie(pydantic.BaseModel):
    """A cookie to inject before page navigation.

    Each cookie needs either ``domain`` or ``url`` (Playwright requirement)."""

    name: str
    value: str
    domain: str | None = None
    path: str | None = None
    url: str | None = None
    expires: float | None = None
    http_only: bool | None = None
    secure: bool | None = None
    same_site: SameSite | None = None

    def to_api_payload(self) -> dict[str, object]:
        out: dict[str, object] = {'name': self.name, 'value': self.value}
        if self.domain is not None:
            out['domain'] = self.domain
        if self.path is not None:
            out['path'] = self.path
        if self.url is not None:
            out['url'] = self.url
        if self.expires is not None:
            out['expires'] = self.expires
        if self.http_only is not None:
            out['http_only'] = self.http_only
        if self.secure is not None:
            out['secure'] = self.secure
        if self.same_site is not None:
            out['same_site'] = self.same_site.value
        return out


class BasicAuth(pydantic.BaseModel):
    """HTTP Basic auth credentials sent on 401 challenge."""

    username: str
    password: str


class CreditBalance(pydantic.BaseModel):
    credits_remaining: int
    plan_id: str
    status: str
    current_period_end: datetime.datetime


class BulkJobResult(pydantic.BaseModel):
    index: int
    job_id: str | None = None
    status: str | None = None
    poll_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class BulkRenderResponse(pydantic.BaseModel):
    submitted: int
    failed: int
    jobs: list[BulkJobResult]
    credits_used: int
    credits_remaining: int
