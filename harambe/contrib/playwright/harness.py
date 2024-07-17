from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Awaitable, Optional, Sequence, Any

from playwright.async_api import async_playwright, BrowserContext, ViewportSize
from playwright_stealth import stealth_async

from harambe.contrib.playwright.impl import PlaywrightPage
from harambe.handlers import UnnecessaryResourceHandler
from harambe.proxy import proxy_from_url
from harambe.types import SetCookieParam

Callback = Callable[[BrowserContext], Awaitable[None]]
PageFactory = Callable[..., Awaitable[PlaywrightPage]]

DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
DEFAULT_VIEWPORT: ViewportSize = {"width": 1280, "height": 1024}


@asynccontextmanager
async def playwright_harness(
    *,
    headless: bool = True,
    cdp_endpoint: str | None = None,
    proxy: str | None = None,
    cookies: Sequence[SetCookieParam] = (),
    stealth: bool = True,
    default_timeout: int = 30000,
    abort_unnecessary_requests: bool = True,
    user_agent: str = DEFAULT_USER_AGENT,
    viewport: Optional[ViewportSize] = None,
    on_start: Optional[Callback] = None,
    on_end: Optional[Callback] = None,
) -> AsyncGenerator[PageFactory, None]:
    """
    Context manager for Playwright. Starts a new browser, context, and page, and closes them when done.
    Also does some basic setup like setting the viewport, user agent, ignoring HTTPS errors,
    creation of HAR file, and stealth.
    """

    async with async_playwright() as p:
        browser = await (
            p.chromium.connect_over_cdp(endpoint_url=cdp_endpoint)
            if cdp_endpoint
            else p.chromium.launch(headless=headless)
        )

        ctx = await browser.new_context(
            viewport=viewport or DEFAULT_VIEWPORT,
            ignore_https_errors=True,
            user_agent=user_agent,
            proxy=proxy_from_url(proxy) if proxy else None,
        )

        ctx.set_default_timeout(default_timeout)

        if cookies:
            await ctx.add_cookies(cookies)

        if abort_unnecessary_requests:
            await ctx.route("**/*", UnnecessaryResourceHandler().handle)

        async def page_factory(*_: Any, **__: Any) -> PlaywrightPage:
            page = await ctx.new_page()
            if stealth:
                await stealth_async(page)
            return page  # type: ignore

        try:
            if on_start:
                await on_start(ctx)
            yield page_factory
        finally:
            try:
                if on_end:
                    await on_end(ctx)
            finally:
                await ctx.close()
                await browser.close()
