from __future__ import annotations

import asyncio
import pathlib
import time
import types

import httpx
import jinja2

from . import exceptions, models

_DEFAULT_BASE_URL = 'https://api.rendershot.io'
_BULK_BATCH_SIZE = 20


class _BaseClient:
    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip('/')
        self._headers = {'X-API-Key': api_key}

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            body = response.json()
        except Exception:
            body = {}
        detail = body.get('detail', response.text) if isinstance(body, dict) else str(body)
        if response.status_code == 401:
            raise exceptions.AuthenticationError(response.status_code, str(detail))
        if response.status_code == 429:
            retry_after = 0
            if isinstance(detail, dict):
                retry_after = int(detail.get('retry_after', 0))
                detail = detail.get('message', str(detail))
            raise exceptions.RateLimitError(response.status_code, str(detail), retry_after)
        raise exceptions.APIError(response.status_code, str(detail))

    def _build_screenshot_payload(
        self,
        *,
        url: str | None = None,
        html: str | None = None,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            'format': format.value,
            'quality': quality,
            'viewport': (viewport or models.ViewportParams()).model_dump(),
            'full_page': full_page,
            'wait_for': wait_for,
            'delay_ms': delay_ms,
        }
        if url is not None:
            payload['url'] = url
        if html is not None:
            payload['html'] = html
        if clip is not None:
            payload['clip'] = clip.model_dump()
        return payload

    def _build_pdf_payload(
        self,
        *,
        url: str | None = None,
        html: str | None = None,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            'format': format.value,
            'orientation': orientation.value,
            'margin': (margin or models.MarginParams()).model_dump(),
            'print_background': print_background,
            'wait_for': wait_for,
            'delay_ms': delay_ms,
        }
        if url is not None:
            payload['url'] = url
        if html is not None:
            payload['html'] = html
        return payload


class RenderShotClient(_BaseClient):
    """Synchronous client for the Rendershot API."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL) -> None:
        super().__init__(api_key, base_url)
        self._http = httpx.Client(headers=self._headers, timeout=120.0)

    def __enter__(self) -> RenderShotClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        self._http.close()

    def close(self) -> None:
        self._http.close()

    # --- internal helpers ---

    def _post(self, path: str, payload: dict[str, object]) -> httpx.Response:
        response = self._http.post(f'{self._base_url}{path}', json=payload)
        self._raise_for_status(response)
        return response

    def _get(self, path: str) -> httpx.Response:
        response = self._http.get(f'{self._base_url}{path}')
        self._raise_for_status(response)
        return response

    def _poll_job(self, job_id: str, poll_interval: float = 2.0, timeout: float = 300.0) -> None:
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() > deadline:
                raise exceptions.JobTimeoutError(job_id, timeout)
            data = self._get(f'/v1/jobs/{job_id}').json()
            status = data.get('status', '')
            if status == 'done':
                return
            if status == 'failed':
                raise exceptions.JobFailedError(job_id, data.get('error', 'unknown error'))
            time.sleep(poll_interval)

    def _bulk_render_and_save(
        self,
        jobs_payload: list[dict[str, object]],
        output_dir: str | pathlib.Path,
        ext: str,
        prefix: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        out = pathlib.Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Split into batches of 20
        batches = [jobs_payload[i : i + _BULK_BATCH_SIZE] for i in range(0, len(jobs_payload), _BULK_BATCH_SIZE)]

        # (original_index, job_id) pairs
        job_ids: list[tuple[int, str]] = []
        global_offset = 0

        for batch in batches:
            response = self._post('/v1/bulk', {'jobs': batch})
            bulk = models.BulkRenderResponse.model_validate(response.json())
            for result in bulk.jobs:
                original_index = global_offset + result.index
                if result.job_id:
                    job_ids.append((original_index, result.job_id))
            global_offset += len(batch)

        # Poll and download each job
        output_paths: list[pathlib.Path | None] = [None] * len(jobs_payload)
        for original_index, job_id in job_ids:
            self._poll_job(job_id, poll_interval=poll_interval, timeout=timeout)
            file_bytes = self._get(f'/v1/jobs/{job_id}/result').content
            dest = out / f'{prefix}_{original_index:04d}.{ext}'
            dest.write_bytes(file_bytes)
            output_paths[original_index] = dest

        return [p for p in output_paths if p is not None]

    # --- single render methods ---

    def screenshot_url(
        self,
        url: str,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> bytes:
        payload = self._build_screenshot_payload(
            url=url, format=format, quality=quality, viewport=viewport,
            full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
        )
        return self._post('/v1/screenshot', payload).content

    def screenshot_url_to_file(
        self,
        url: str,
        output_path: str | pathlib.Path,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> pathlib.Path:
        data = self.screenshot_url(
            url, format=format, quality=quality, viewport=viewport,
            full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
        )
        dest = pathlib.Path(output_path)
        dest.write_bytes(data)
        return dest

    def screenshot_html(
        self,
        html: str,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> bytes:
        payload = self._build_screenshot_payload(
            html=html, format=format, quality=quality, viewport=viewport,
            full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
        )
        return self._post('/v1/screenshot', payload).content

    def screenshot_html_to_file(
        self,
        html: str,
        output_path: str | pathlib.Path,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> pathlib.Path:
        data = self.screenshot_html(
            html, format=format, quality=quality, viewport=viewport,
            full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
        )
        dest = pathlib.Path(output_path)
        dest.write_bytes(data)
        return dest

    def pdf_url(
        self,
        url: str,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> bytes:
        payload = self._build_pdf_payload(
            url=url, format=format, orientation=orientation, margin=margin,
            print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
        )
        return self._post('/v1/pdf', payload).content

    def pdf_url_to_file(
        self,
        url: str,
        output_path: str | pathlib.Path,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> pathlib.Path:
        data = self.pdf_url(
            url, format=format, orientation=orientation, margin=margin,
            print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
        )
        dest = pathlib.Path(output_path)
        dest.write_bytes(data)
        return dest

    def pdf_html(
        self,
        html: str,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> bytes:
        payload = self._build_pdf_payload(
            html=html, format=format, orientation=orientation, margin=margin,
            print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
        )
        return self._post('/v1/pdf', payload).content

    def pdf_html_to_file(
        self,
        html: str,
        output_path: str | pathlib.Path,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> pathlib.Path:
        data = self.pdf_html(
            html, format=format, orientation=orientation, margin=margin,
            print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
        )
        dest = pathlib.Path(output_path)
        dest.write_bytes(data)
        return dest

    # --- balance ---

    def get_balance(self) -> models.CreditBalance:
        return models.CreditBalance.model_validate(self._get('/v1/balance').json())

    # --- bulk methods ---

    def bulk_screenshot_urls(
        self,
        urls: list[str],
        output_dir: str | pathlib.Path,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        jobs = [
            {**self._build_screenshot_payload(
                url=url, format=format, quality=quality, viewport=viewport,
                full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
            ), 'type': 'screenshot'}
            for url in urls
        ]
        ext = format.value
        return self._bulk_render_and_save(jobs, output_dir, ext, 'screenshot', poll_interval, timeout)

    def bulk_screenshot_htmls(
        self,
        htmls: list[str],
        output_dir: str | pathlib.Path,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        jobs = [
            {**self._build_screenshot_payload(
                html=html, format=format, quality=quality, viewport=viewport,
                full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
            ), 'type': 'screenshot'}
            for html in htmls
        ]
        ext = format.value
        return self._bulk_render_and_save(jobs, output_dir, ext, 'screenshot', poll_interval, timeout)

    def bulk_pdf_urls(
        self,
        urls: list[str],
        output_dir: str | pathlib.Path,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        jobs = [
            {**self._build_pdf_payload(
                url=url, format=format, orientation=orientation, margin=margin,
                print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
            ), 'type': 'pdf'}
            for url in urls
        ]
        return self._bulk_render_and_save(jobs, output_dir, 'pdf', 'pdf', poll_interval, timeout)

    def bulk_pdf_htmls(
        self,
        htmls: list[str],
        output_dir: str | pathlib.Path,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        jobs = [
            {**self._build_pdf_payload(
                html=html, format=format, orientation=orientation, margin=margin,
                print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
            ), 'type': 'pdf'}
            for html in htmls
        ]
        return self._bulk_render_and_save(jobs, output_dir, 'pdf', 'pdf', poll_interval, timeout)

    def bulk_pdf_from_template(
        self,
        template_str: str,
        contexts: list[dict[str, object]],
        output_dir: str | pathlib.Path,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        env = jinja2.Environment(autoescape=jinja2.select_autoescape(['html']))
        tmpl = env.from_string(template_str)
        htmls = [tmpl.render(**ctx) for ctx in contexts]
        return self.bulk_pdf_htmls(
            htmls, output_dir,
            format=format, orientation=orientation, margin=margin,
            print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
            poll_interval=poll_interval, timeout=timeout,
        )


class AsyncRenderShotClient(_BaseClient):
    """Asynchronous client for the Rendershot API."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL) -> None:
        super().__init__(api_key, base_url)
        self._http = httpx.AsyncClient(headers=self._headers, timeout=120.0)

    async def __aenter__(self) -> AsyncRenderShotClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        await self._http.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- internal helpers ---

    async def _post(self, path: str, payload: dict[str, object]) -> httpx.Response:
        response = await self._http.post(f'{self._base_url}{path}', json=payload)
        self._raise_for_status(response)
        return response

    async def _get(self, path: str) -> httpx.Response:
        response = await self._http.get(f'{self._base_url}{path}')
        self._raise_for_status(response)
        return response

    async def _poll_job(self, job_id: str, poll_interval: float = 2.0, timeout: float = 300.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            if asyncio.get_event_loop().time() > deadline:
                raise exceptions.JobTimeoutError(job_id, timeout)
            data = (await self._get(f'/v1/jobs/{job_id}')).json()
            status = data.get('status', '')
            if status == 'done':
                return
            if status == 'failed':
                raise exceptions.JobFailedError(job_id, data.get('error', 'unknown error'))
            await asyncio.sleep(poll_interval)

    async def _bulk_render_and_save(
        self,
        jobs_payload: list[dict[str, object]],
        output_dir: str | pathlib.Path,
        ext: str,
        prefix: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        out = pathlib.Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        batches = [jobs_payload[i : i + _BULK_BATCH_SIZE] for i in range(0, len(jobs_payload), _BULK_BATCH_SIZE)]

        job_ids: list[tuple[int, str]] = []
        global_offset = 0

        for batch in batches:
            response = await self._post('/v1/bulk', {'jobs': batch})
            bulk = models.BulkRenderResponse.model_validate(response.json())
            for result in bulk.jobs:
                original_index = global_offset + result.index
                if result.job_id:
                    job_ids.append((original_index, result.job_id))
            global_offset += len(batch)

        async def _fetch_one(original_index: int, job_id: str) -> tuple[int, bytes]:
            await self._poll_job(job_id, poll_interval=poll_interval, timeout=timeout)
            content = (await self._get(f'/v1/jobs/{job_id}/result')).content
            return original_index, content

        results = await asyncio.gather(*[_fetch_one(idx, jid) for idx, jid in job_ids])

        output_paths: list[pathlib.Path | None] = [None] * len(jobs_payload)
        for original_index, file_bytes in results:
            dest = out / f'{prefix}_{original_index:04d}.{ext}'
            dest.write_bytes(file_bytes)
            output_paths[original_index] = dest

        return [p for p in output_paths if p is not None]

    # --- single render methods ---

    async def screenshot_url(
        self,
        url: str,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> bytes:
        payload = self._build_screenshot_payload(
            url=url, format=format, quality=quality, viewport=viewport,
            full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
        )
        return (await self._post('/v1/screenshot', payload)).content

    async def screenshot_url_to_file(
        self,
        url: str,
        output_path: str | pathlib.Path,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> pathlib.Path:
        data = await self.screenshot_url(
            url, format=format, quality=quality, viewport=viewport,
            full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
        )
        dest = pathlib.Path(output_path)
        dest.write_bytes(data)
        return dest

    async def screenshot_html(
        self,
        html: str,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> bytes:
        payload = self._build_screenshot_payload(
            html=html, format=format, quality=quality, viewport=viewport,
            full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
        )
        return (await self._post('/v1/screenshot', payload)).content

    async def screenshot_html_to_file(
        self,
        html: str,
        output_path: str | pathlib.Path,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> pathlib.Path:
        data = await self.screenshot_html(
            html, format=format, quality=quality, viewport=viewport,
            full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
        )
        dest = pathlib.Path(output_path)
        dest.write_bytes(data)
        return dest

    async def pdf_url(
        self,
        url: str,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> bytes:
        payload = self._build_pdf_payload(
            url=url, format=format, orientation=orientation, margin=margin,
            print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
        )
        return (await self._post('/v1/pdf', payload)).content

    async def pdf_url_to_file(
        self,
        url: str,
        output_path: str | pathlib.Path,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> pathlib.Path:
        data = await self.pdf_url(
            url, format=format, orientation=orientation, margin=margin,
            print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
        )
        dest = pathlib.Path(output_path)
        dest.write_bytes(data)
        return dest

    async def pdf_html(
        self,
        html: str,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> bytes:
        payload = self._build_pdf_payload(
            html=html, format=format, orientation=orientation, margin=margin,
            print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
        )
        return (await self._post('/v1/pdf', payload)).content

    async def pdf_html_to_file(
        self,
        html: str,
        output_path: str | pathlib.Path,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
    ) -> pathlib.Path:
        data = await self.pdf_html(
            html, format=format, orientation=orientation, margin=margin,
            print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
        )
        dest = pathlib.Path(output_path)
        dest.write_bytes(data)
        return dest

    # --- balance ---

    async def get_balance(self) -> models.CreditBalance:
        return models.CreditBalance.model_validate((await self._get('/v1/balance')).json())

    # --- bulk methods ---

    async def bulk_screenshot_urls(
        self,
        urls: list[str],
        output_dir: str | pathlib.Path,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        jobs = [
            {**self._build_screenshot_payload(
                url=url, format=format, quality=quality, viewport=viewport,
                full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
            ), 'type': 'screenshot'}
            for url in urls
        ]
        ext = format.value
        return await self._bulk_render_and_save(jobs, output_dir, ext, 'screenshot', poll_interval, timeout)

    async def bulk_screenshot_htmls(
        self,
        htmls: list[str],
        output_dir: str | pathlib.Path,
        *,
        format: models.ScreenshotFormat = models.ScreenshotFormat.png,
        quality: int = 85,
        viewport: models.ViewportParams | None = None,
        full_page: bool = False,
        clip: models.ClipParams | None = None,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        jobs = [
            {**self._build_screenshot_payload(
                html=html, format=format, quality=quality, viewport=viewport,
                full_page=full_page, clip=clip, wait_for=wait_for, delay_ms=delay_ms,
            ), 'type': 'screenshot'}
            for html in htmls
        ]
        ext = format.value
        return await self._bulk_render_and_save(jobs, output_dir, ext, 'screenshot', poll_interval, timeout)

    async def bulk_pdf_urls(
        self,
        urls: list[str],
        output_dir: str | pathlib.Path,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        jobs = [
            {**self._build_pdf_payload(
                url=url, format=format, orientation=orientation, margin=margin,
                print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
            ), 'type': 'pdf'}
            for url in urls
        ]
        return await self._bulk_render_and_save(jobs, output_dir, 'pdf', 'pdf', poll_interval, timeout)

    async def bulk_pdf_htmls(
        self,
        htmls: list[str],
        output_dir: str | pathlib.Path,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        jobs = [
            {**self._build_pdf_payload(
                html=html, format=format, orientation=orientation, margin=margin,
                print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
            ), 'type': 'pdf'}
            for html in htmls
        ]
        return await self._bulk_render_and_save(jobs, output_dir, 'pdf', 'pdf', poll_interval, timeout)

    async def bulk_pdf_from_template(
        self,
        template_str: str,
        contexts: list[dict[str, object]],
        output_dir: str | pathlib.Path,
        *,
        format: models.PDFFormat = models.PDFFormat.A4,
        orientation: models.PDFOrientation = models.PDFOrientation.portrait,
        margin: models.MarginParams | None = None,
        print_background: bool = True,
        wait_for: str = 'networkidle',
        delay_ms: int = 0,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> list[pathlib.Path]:
        env = jinja2.Environment(autoescape=jinja2.select_autoescape(['html']))
        tmpl = env.from_string(template_str)
        htmls = [tmpl.render(**ctx) for ctx in contexts]
        return await self.bulk_pdf_htmls(
            htmls, output_dir,
            format=format, orientation=orientation, margin=margin,
            print_background=print_background, wait_for=wait_for, delay_ms=delay_ms,
            poll_interval=poll_interval, timeout=timeout,
        )
