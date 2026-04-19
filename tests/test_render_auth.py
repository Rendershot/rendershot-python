"""Authenticated-render options: headers, cookies, basic_auth."""

from __future__ import annotations

import json

import httpx
import respx

import rendershot

_API_KEY = 'test-key-123'
_FAKE_PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100


def _last_json(route: respx.Route) -> dict[str, object]:
    request = route.calls.last.request
    return json.loads(request.content)


class TestAuthFields:
    def test_headers_forwarded(self, mock_api: respx.MockRouter) -> None:
        route = mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        client = rendershot.RenderShotClient(_API_KEY)
        client.screenshot_url(
            'https://httpbin.org/headers',
            headers={'Authorization': 'Bearer abc', 'X-Tenant': 'acme'},
        )
        sent = _last_json(route)
        assert sent['headers'] == {'Authorization': 'Bearer abc', 'X-Tenant': 'acme'}

    def test_cookies_forwarded_with_snake_case(self, mock_api: respx.MockRouter) -> None:
        route = mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        client = rendershot.RenderShotClient(_API_KEY)
        client.screenshot_url(
            'https://example.com',
            cookies=[
                rendershot.models.Cookie(
                    name='sid',
                    value='abc',
                    domain='example.com',
                    path='/',
                    http_only=True,
                    secure=True,
                    same_site=rendershot.models.SameSite.lax,
                )
            ],
        )
        sent = _last_json(route)
        assert sent['cookies'] == [
            {
                'name': 'sid',
                'value': 'abc',
                'domain': 'example.com',
                'path': '/',
                'http_only': True,
                'secure': True,
                'same_site': 'Lax',
            }
        ]

    def test_basic_auth_forwarded(self, mock_api: respx.MockRouter) -> None:
        route = mock_api.post('/v1/pdf').mock(return_value=httpx.Response(200, content=b'%PDF-1.4'))
        client = rendershot.RenderShotClient(_API_KEY)
        client.pdf_url(
            'https://staging.example.com',
            basic_auth=rendershot.models.BasicAuth(username='u', password='p'),
        )
        sent = _last_json(route)
        assert sent['basic_auth'] == {'username': 'u', 'password': 'p'}

    def test_auth_fields_omitted_when_not_set(self, mock_api: respx.MockRouter) -> None:
        route = mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        client = rendershot.RenderShotClient(_API_KEY)
        client.screenshot_url('https://example.com')
        sent = _last_json(route)
        assert 'headers' not in sent
        assert 'cookies' not in sent
        assert 'basic_auth' not in sent

    def test_headers_on_html_screenshot(self, mock_api: respx.MockRouter) -> None:
        route = mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        client = rendershot.RenderShotClient(_API_KEY)
        client.screenshot_html('<h1>x</h1>', headers={'X-A': '1'})
        sent = _last_json(route)
        assert sent['headers'] == {'X-A': '1'}

    def test_headers_on_pdf_html(self, mock_api: respx.MockRouter) -> None:
        route = mock_api.post('/v1/pdf').mock(return_value=httpx.Response(200, content=b'%PDF'))
        client = rendershot.RenderShotClient(_API_KEY)
        client.pdf_html('<h1>x</h1>', headers={'X-A': '1'})
        sent = _last_json(route)
        assert sent['headers'] == {'X-A': '1'}

    def test_auth_forwarded_in_to_file_methods(
        self, mock_api: respx.MockRouter, tmp_path
    ) -> None:  # type: ignore[no-untyped-def]
        route = mock_api.post('/v1/screenshot').mock(return_value=httpx.Response(200, content=_FAKE_PNG))
        client = rendershot.RenderShotClient(_API_KEY)
        client.screenshot_url_to_file(
            'https://example.com',
            tmp_path / 'out.png',
            basic_auth=rendershot.models.BasicAuth(username='u', password='p'),
        )
        sent = _last_json(route)
        assert sent['basic_auth'] == {'username': 'u', 'password': 'p'}
