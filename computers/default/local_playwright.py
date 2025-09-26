from playwright.sync_api import Browser, Page
from ..shared.base_playwright import BasePlaywrightComputer


class LocalPlaywrightBrowser(BasePlaywrightComputer):
    """Launches a local Chromium instance using Playwright."""

    def __init__(self, headless: bool = False):
        super().__init__()
        self.headless = headless

    def get_dimensions(self) -> tuple[int, int]:
        """Return a larger default window size for the local browser."""
        return 1600, 900

    def _apply_page_settings(self, page: Page) -> None:
        """Ensure every page matches the desired viewport and zoom level."""
        width, height = self.get_dimensions()
        page.set_viewport_size({"width": width, "height": height})

        page.evaluate(
            """
            (() => {
                const applyZoom = () => {
                    if (document && document.body) {
                        document.body.style.zoom = '75%';
                    }
                };

                if (document.readyState === 'complete' || document.readyState === 'interactive') {
                    applyZoom();
                } else {
                    document.addEventListener('DOMContentLoaded', applyZoom, { once: true });
                }
            })();
            """
        )

    def _get_browser_and_page(self) -> tuple[Browser, Page]:
        width, height = self.get_dimensions()
        launch_args = [
            f"--window-size={width},{height}",
            "--disable-extensions",
            "--disable-file-system",
        ]
        browser = self._playwright.chromium.launch(
            chromium_sandbox=True,
            headless=self.headless,
            args=launch_args,
            env={"DISPLAY": ":0"},
        )

        context = browser.new_context()

        # Add event listeners for page creation and closure
        context.on("page", self._handle_new_page)

        page = context.new_page()
        self._apply_page_settings(page)
        page.on("close", self._handle_page_close)

        page.goto("https://bing.com")

        return browser, page

    def _handle_new_page(self, page: Page):
        """Handle the creation of a new page."""
        print("New page created")
        self._page = page
        self._apply_page_settings(page)
        page.on("close", self._handle_page_close)

    def _handle_page_close(self, page: Page):
        """Handle the closure of a page."""
        print("Page closed")
        if self._page == page:
            if self._browser.contexts[0].pages:
                self._page = self._browser.contexts[0].pages[-1]
            else:
                print("Warning: All pages have been closed.")
                self._page = None
