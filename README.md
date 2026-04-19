# rendershot-python

[![CI](https://github.com/Rendershot/rendershot-python/actions/workflows/ci.yml/badge.svg)](https://github.com/Rendershot/rendershot-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rendershot)](https://pypi.org/project/rendershot/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Python SDK for the [Rendershot](https://rendershot.io) screenshot & PDF generation API.

## Installation

```bash
pip install rendershot
```

## Quick start

```python
import rendershot

# Sync client
client = rendershot.RenderShotClient(api_key='your-api-key')

# Capture a screenshot
png_bytes = client.screenshot_url('https://example.com')

# Save directly to a file
client.screenshot_url_to_file('https://example.com', 'screenshot.png')

# Render a PDF
pdf_bytes = client.pdf_url('https://example.com')
client.pdf_html_to_file('<h1>Hello</h1>', 'output.pdf')

# Check your balance
balance = client.get_balance()
print(balance.credits_remaining)
```

## Async client

```python
import asyncio
import rendershot

async def main():
    async with rendershot.AsyncRenderShotClient(api_key='your-api-key') as client:
        png = await client.screenshot_url('https://example.com')
        await client.pdf_url_to_file('https://example.com', 'report.pdf')

asyncio.run(main())
```

## Bulk rendering

All bulk methods submit jobs via the `/v1/bulk` endpoint, poll until complete, and save results to a folder.

```python
# Bulk screenshots from URLs
paths = client.bulk_screenshot_urls(
    ['https://example.com', 'https://github.com'],
    output_dir='/tmp/screenshots',
)

# Bulk PDFs from an HTML Jinja2 template (great for invoices)
template = '''
<html><body>
  <h1>Invoice #{{ invoice_id }}</h1>
  <p>Amount: ${{ amount }}</p>
</body></html>
'''
paths = client.bulk_pdf_from_template(
    template,
    contexts=[
        {'invoice_id': 1001, 'amount': '99.00'},
        {'invoice_id': 1002, 'amount': '149.00'},
    ],
    output_dir='/tmp/invoices',
)
```

## AI cleanup (remove cookie banners & popups)

Pass `ai_cleanup` to have the backend strip common cookie banners, consent overlays, and popup modals before the render. Two modes:

- `AICleanupMode.fast` — JS heuristics (1 credit, same as a plain render).
- `AICleanupMode.thorough` — adds a Claude LLM pass that snapshots the DOM and identifies remaining overlays (3 credits; backend must have an Anthropic key configured).

```python
png = client.screenshot_url(
    'https://example.com',
    ai_cleanup=rendershot.models.AICleanupMode.fast,
)

pdf = client.pdf_url(
    'https://example.com',
    ai_cleanup=rendershot.models.AICleanupMode.thorough,
)
```

Works on all single and bulk methods on both the sync and async clients.

## Authenticated pages

Render pages behind a login by sending custom HTTP headers, session cookies, or HTTP Basic auth alongside the URL. Credentials are never persisted — they only ride on the request payload.

```python
# Bearer token + session cookie
png = client.screenshot_url(
    'https://app.example.com/dashboard',
    headers={'Authorization': 'Bearer sk_internal_...', 'X-Tenant-Id': 'acme'},
    cookies=[
        rendershot.models.Cookie(
            name='session_id',
            value='eyJhbGciOi...',
            domain='app.example.com',
            path='/',
            secure=True,
            http_only=True,
            same_site=rendershot.models.SameSite.lax,
        ),
    ],
)

# HTTP Basic auth
pdf = client.pdf_url(
    'https://staging.example.com/report',
    basic_auth=rendershot.models.BasicAuth(username='staging', password='hunter2'),
)
```

Reserved header names (`Host`, `Cookie`, `Content-Length`, `Sec-*`, `Connection`) are rejected server-side. Max 30 headers / 50 cookies per request; header values up to 2 KB.

## Verifying webhook signatures

Rendershot signs every outbound webhook POST with HMAC-SHA256 over `"{timestamp}.{body}"` using the per-endpoint secret shown on the Webhooks dashboard. Use the SDK helpers in your receiver to reject forged or replayed requests.

```python
from flask import Flask, request, abort
import rendershot

WEBHOOK_SECRET = 'your-endpoint-secret'  # from the dashboard

app = Flask(__name__)

@app.post('/rendershot-webhook')
def receive():
    ok = rendershot.is_valid_signature(
        secret=WEBHOOK_SECRET,
        body=request.data,
        signature_header=request.headers.get('X-Rendershot-Signature', ''),
        timestamp_header=request.headers.get('X-Rendershot-Timestamp', ''),
    )
    if not ok:
        abort(400)
    payload = request.get_json()
    # ... handle job.completed / job.failed ...
    return '', 200
```

`verify_signature` raises `rendershot.WebhookVerificationError` instead of returning a bool if you prefer exception-based flow. Both accept `max_age_seconds=300` (default) to bound replay attacks.

## Handling network_idle timeouts

Some URLs never reach `network_idle` (e.g. sites with persistent WebSocket connections or infinite polling). Use `timeout_fallback_to='dom_content_loaded'` to automatically retry with `wait_for='dom_content_loaded'` when a timeout occurs:

```python
# Single URL — retries automatically on timeout
png = client.screenshot_url(
    'https://example.com',
    wait_for='network_idle',
    timeout_fallback_to='dom_content_loaded',
)

# Save to file
client.screenshot_url_to_file(
    'https://example.com',
    'sport5.png',
    wait_for='network_idle',
    timeout_fallback_to='dom_content_loaded',
)

# Bulk — each timed-out job is individually retried
paths = client.bulk_screenshot_urls(
    urls=['https://example.com', 'https://example2.com'],
    output_dir='./screenshots',
    wait_for='network_idle',
    timeout_fallback_to='dom_content_loaded',
)
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | required | Your Rendershot API key |
| `base_url` | `https://api.rendershot.io` | API base URL |

Bulk methods also accept `poll_interval` (seconds, default `2.0`) and `timeout` (seconds, default `300.0`).

## Error handling

```python
from rendershot import exceptions

try:
    client.screenshot_url('https://example.com')
except exceptions.AuthenticationError:
    print('Invalid API key')
except exceptions.RateLimitError as e:
    print(f'Rate limited, retry after {e.retry_after}s')
except exceptions.JobFailedError as e:
    print(f'Job {e.job_id} failed')
except exceptions.APIError as e:
    print(f'API error {e.status_code}: {e.detail}')
```
