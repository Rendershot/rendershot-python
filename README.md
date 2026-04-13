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

## Handling networkidle timeouts

Some URLs never reach `networkidle` (e.g. sites with persistent WebSocket connections or infinite polling). Use `timeout_fallback_to='domcontentloaded'` to automatically retry with `wait_for='domcontentloaded'` when a timeout occurs:

```python
# Single URL — retries automatically on timeout
png = client.screenshot_url(
    'https://example.com',
    timeout_fallback_to='domcontentloaded',
)

# Save to file
client.screenshot_url_to_file(
    'https://example.com',
    'sport5.png',
    timeout_fallback_to='domcontentloaded',
)

# Bulk — each timed-out job is individually retried
paths = client.bulk_screenshot_urls(
    urls=['https://example.com', 'https://example2.com'],
    output_dir='./screenshots',
    timeout_fallback_to='domcontentloaded',
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
