from __future__ import annotations

import datetime
import pathlib

import httpx
import pytest
import respx

import rendershot

_API_KEY = 'test-key-123'
_FAKE_PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
_FAKE_PDF = b'%PDF-1.4' + b'\x00' * 100
_JOB_ID = 'job-abc-123'

_BALANCE_PAYLOAD = {
    'credits_remaining': 50,
    'plan_id': 'free',
    'status': 'active',
    'current_period_end': '2026-05-01T00:00:00Z',
}

_BULK_RESPONSE = {
    'submitted': 1,
    'failed': 0,
    'credits_used': 1,
    'credits_remaining': 49,
    'jobs': [
        {'index': 0, 'job_id': _JOB_ID, 'status': 'queued', 'poll_url': f'/v1/jobs/{_JOB_ID}'},
    ],
}

_JOB_DONE = {'status': 'done', 'job_id': _JOB_ID}
_JOB_FAILED = {'status': 'failed', 'job_id': _JOB_ID, 'error': 'render error'}


# --- sync client ---


class TestRenderShotClient:
    def test_screenshot_url(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        client = rendershot.RenderShotClient(_API_KEY)
        result = client.screenshot_url('https://example.com')
        assert result == _FAKE_PNG

    def test_screenshot_html(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        client = rendershot.RenderShotClient(_API_KEY)
        result = client.screenshot_html('<h1>Hello</h1>')
        assert result == _FAKE_PNG

    def test_screenshot_url_to_file(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        client = rendershot.RenderShotClient(_API_KEY)
        dest = tmp_path / 'out.png'
        result = client.screenshot_url_to_file('https://example.com', dest)
        assert result == dest
        assert dest.read_bytes() == _FAKE_PNG

    def test_screenshot_html_to_file(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        client = rendershot.RenderShotClient(_API_KEY)
        dest = tmp_path / 'out.png'
        result = client.screenshot_html_to_file('<h1>Hello</h1>', dest)
        assert result == dest
        assert dest.read_bytes() == _FAKE_PNG

    def test_pdf_url(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/pdf').mock(return_value=httpx.Response(200, content=_FAKE_PDF))
        client = rendershot.RenderShotClient(_API_KEY)
        result = client.pdf_url('https://example.com')
        assert result == _FAKE_PDF

    def test_pdf_html(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/pdf').mock(return_value=httpx.Response(200, content=_FAKE_PDF))
        client = rendershot.RenderShotClient(_API_KEY)
        result = client.pdf_html('<h1>Invoice</h1>')
        assert result == _FAKE_PDF

    def test_pdf_url_to_file(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/pdf').mock(return_value=httpx.Response(200, content=_FAKE_PDF))
        client = rendershot.RenderShotClient(_API_KEY)
        dest = tmp_path / 'out.pdf'
        result = client.pdf_url_to_file('https://example.com', dest)
        assert result == dest
        assert dest.read_bytes() == _FAKE_PDF

    def test_pdf_html_to_file(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/pdf').mock(return_value=httpx.Response(200, content=_FAKE_PDF))
        client = rendershot.RenderShotClient(_API_KEY)
        dest = tmp_path / 'out.pdf'
        result = client.pdf_html_to_file('<h1>Invoice</h1>', dest)
        assert result == dest
        assert dest.read_bytes() == _FAKE_PDF

    def test_get_balance(self, mock_api: respx.MockRouter) -> None:
        mock_api.get('/v1/balance').mock(return_value=httpx.Response(200, json=_BALANCE_PAYLOAD))
        client = rendershot.RenderShotClient(_API_KEY)
        balance = client.get_balance()
        assert balance.credits_remaining == 50
        assert balance.plan_id == 'free'
        assert isinstance(balance.current_period_end, datetime.datetime)

    def test_authentication_error(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/screenshot').mock(
            return_value=httpx.Response(401, json={'detail': 'Invalid API key'})
        )
        client = rendershot.RenderShotClient(_API_KEY)
        with pytest.raises(rendershot.exceptions.AuthenticationError) as exc_info:
            client.screenshot_url('https://example.com')
        assert exc_info.value.status_code == 401

    def test_rate_limit_error(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/screenshot').mock(
            return_value=httpx.Response(
                429,
                json={'detail': {'code': 'RATE_LIMIT_EXCEEDED', 'message': 'Too many requests', 'retry_after': 30}},
            )
        )
        client = rendershot.RenderShotClient(_API_KEY)
        with pytest.raises(rendershot.exceptions.RateLimitError) as exc_info:
            client.screenshot_url('https://example.com')
        assert exc_info.value.retry_after == 30

    def test_api_error(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/screenshot').mock(
            return_value=httpx.Response(500, json={'detail': 'Internal server error'})
        )
        client = rendershot.RenderShotClient(_API_KEY)
        with pytest.raises(rendershot.exceptions.APIError) as exc_info:
            client.screenshot_url('https://example.com')
        assert exc_info.value.status_code == 500

    def test_context_manager(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        with rendershot.RenderShotClient(_API_KEY) as client:
            result = client.screenshot_url('https://example.com')
        assert result == _FAKE_PNG

    def test_bulk_screenshot_urls(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/bulk').mock(return_value=httpx.Response(200, json=_BULK_RESPONSE))
        mock_api.get(f'/v1/jobs/{_JOB_ID}').mock(return_value=httpx.Response(200, json=_JOB_DONE))
        mock_api.get(f'/v1/jobs/{_JOB_ID}/result').mock(return_value=httpx.Response(200, content=_FAKE_PNG))

        client = rendershot.RenderShotClient(_API_KEY)
        paths = client.bulk_screenshot_urls(['https://example.com'], tmp_path)
        assert len(paths) == 1
        assert paths[0].suffix == '.png'
        assert paths[0].read_bytes() == _FAKE_PNG

    def test_bulk_pdf_from_template(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/bulk').mock(return_value=httpx.Response(200, json=_BULK_RESPONSE))
        mock_api.get(f'/v1/jobs/{_JOB_ID}').mock(return_value=httpx.Response(200, json=_JOB_DONE))
        mock_api.get(f'/v1/jobs/{_JOB_ID}/result').mock(return_value=httpx.Response(200, content=_FAKE_PDF))

        template = '<h1>Invoice #{{ number }}</h1>'
        client = rendershot.RenderShotClient(_API_KEY)
        paths = client.bulk_pdf_from_template(template, [{'number': 1}], tmp_path)
        assert len(paths) == 1
        assert paths[0].suffix == '.pdf'

    def test_bulk_job_failed(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/bulk').mock(return_value=httpx.Response(200, json=_BULK_RESPONSE))
        mock_api.get(f'/v1/jobs/{_JOB_ID}').mock(return_value=httpx.Response(200, json=_JOB_FAILED))

        client = rendershot.RenderShotClient(_API_KEY)
        with pytest.raises(rendershot.exceptions.JobFailedError):
            client.bulk_screenshot_urls(['https://example.com'], tmp_path)

    def test_api_key_sent_in_header(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        client = rendershot.RenderShotClient(_API_KEY)
        client.screenshot_url('https://example.com')
        request = mock_api.calls.last.request
        assert request.headers['x-api-key'] == _API_KEY


# --- async client ---


class TestAsyncRenderShotClient:
    async def test_screenshot_url(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            result = await client.screenshot_url('https://example.com')
        assert result == _FAKE_PNG

    async def test_screenshot_html(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            result = await client.screenshot_html('<h1>Hello</h1>')
        assert result == _FAKE_PNG

    async def test_screenshot_url_to_file(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        dest = tmp_path / 'out.png'
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            result = await client.screenshot_url_to_file('https://example.com', dest)
        assert result == dest
        assert dest.read_bytes() == _FAKE_PNG

    async def test_screenshot_html_to_file(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        dest = tmp_path / 'out.png'
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            result = await client.screenshot_html_to_file('<h1>Hello</h1>', dest)
        assert result == dest
        assert dest.read_bytes() == _FAKE_PNG

    async def test_pdf_url(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/pdf').mock(return_value=httpx.Response(200, content=_FAKE_PDF))
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            result = await client.pdf_url('https://example.com')
        assert result == _FAKE_PDF

    async def test_pdf_html(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/pdf').mock(return_value=httpx.Response(200, content=_FAKE_PDF))
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            result = await client.pdf_html('<h1>Invoice</h1>')
        assert result == _FAKE_PDF

    async def test_pdf_url_to_file(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/pdf').mock(return_value=httpx.Response(200, content=_FAKE_PDF))
        dest = tmp_path / 'out.pdf'
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            result = await client.pdf_url_to_file('https://example.com', dest)
        assert result == dest
        assert dest.read_bytes() == _FAKE_PDF

    async def test_pdf_html_to_file(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/pdf').mock(return_value=httpx.Response(200, content=_FAKE_PDF))
        dest = tmp_path / 'out.pdf'
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            result = await client.pdf_html_to_file('<h1>Invoice</h1>', dest)
        assert result == dest
        assert dest.read_bytes() == _FAKE_PDF

    async def test_get_balance(self, mock_api: respx.MockRouter) -> None:
        mock_api.get('/v1/balance').mock(return_value=httpx.Response(200, json=_BALANCE_PAYLOAD))
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            balance = await client.get_balance()
        assert balance.credits_remaining == 50

    async def test_authentication_error(self, mock_api: respx.MockRouter) -> None:
        mock_api.post('/v1/screenshot').mock(
            return_value=httpx.Response(401, json={'detail': 'Invalid API key'})
        )
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            with pytest.raises(rendershot.exceptions.AuthenticationError):
                await client.screenshot_url('https://example.com')

    async def test_bulk_screenshot_urls(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/bulk').mock(return_value=httpx.Response(200, json=_BULK_RESPONSE))
        mock_api.get(f'/v1/jobs/{_JOB_ID}').mock(return_value=httpx.Response(200, json=_JOB_DONE))
        mock_api.get(f'/v1/jobs/{_JOB_ID}/result').mock(return_value=httpx.Response(200, content=_FAKE_PNG))

        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            paths = await client.bulk_screenshot_urls(['https://example.com'], tmp_path)
        assert len(paths) == 1
        assert paths[0].read_bytes() == _FAKE_PNG

    async def test_bulk_pdf_from_template(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/bulk').mock(return_value=httpx.Response(200, json=_BULK_RESPONSE))
        mock_api.get(f'/v1/jobs/{_JOB_ID}').mock(return_value=httpx.Response(200, json=_JOB_DONE))
        mock_api.get(f'/v1/jobs/{_JOB_ID}/result').mock(return_value=httpx.Response(200, content=_FAKE_PDF))

        template = '<h1>Invoice #{{ number }}</h1>'
        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            paths = await client.bulk_pdf_from_template(template, [{'number': 1}], tmp_path)
        assert len(paths) == 1
        assert paths[0].suffix == '.pdf'

    async def test_bulk_job_failed(self, mock_api: respx.MockRouter, tmp_path: pathlib.Path) -> None:
        mock_api.post('/v1/bulk').mock(return_value=httpx.Response(200, json=_BULK_RESPONSE))
        mock_api.get(f'/v1/jobs/{_JOB_ID}').mock(return_value=httpx.Response(200, json=_JOB_FAILED))

        async with rendershot.AsyncRenderShotClient(_API_KEY) as client:
            with pytest.raises(rendershot.exceptions.JobFailedError):
                await client.bulk_screenshot_urls(['https://example.com'], tmp_path)
