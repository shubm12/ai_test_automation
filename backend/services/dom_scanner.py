"""Stage 0 — DOM grounding.

Walks the real target app with Playwright, replaying a resolved flow (see
flow_resolver.py), and extracts every interactive element with a ranked real
selector: data-testid > id > name > text. This is the anti-hallucination
foundation for every later stage - the LLM is only ever shown selectors that
were actually observed on the live page.
"""
from flows.definitions import FlowStep

EXTRACT_SCRIPT = """
() => {
    const nodes = document.querySelectorAll('button, a, input, select, [role="button"]');
    const out = [];
    nodes.forEach(el => {
        out.push({
            tag: el.tagName.toLowerCase(),
            text: (el.innerText || el.value || '').trim(),
            id: el.id || null,
            testId: el.getAttribute('data-testid'),
            name: el.getAttribute('name'),
            type: el.type || null,
            placeholder: el.getAttribute('placeholder'),
            ariaLabel: el.getAttribute('aria-label')
        });
    });
    return out;
}
"""


def rank_selector(el: dict) -> str | None:
    if el.get("testId"):
        return f'[data-testid="{el["testId"]}"]'
    if el.get("id"):
        return f'#{el["id"]}'
    if el.get("name"):
        return f'[name="{el["name"]}"]'
    if el.get("text"):
        return f'text="{el["text"]}"'
    return None


def clean_elements(raw_elements: list[dict], page_label: str) -> list[dict]:
    results = []
    for el in raw_elements:
        selector = rank_selector(el)
        if selector:
            el["recommended_selector"] = selector
            el["page"] = page_label
            results.append(el)
    return results


class DomScannerService:
    async def scan(self, url: str, flow_steps: list[FlowStep]) -> list[dict]:
        from playwright.async_api import async_playwright

        all_elements: list[dict] = []
        page_counter = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            page = await browser.new_page()

            for step in flow_steps:
                action = step.get("action")

                if action == "navigate":
                    target = step.get("target", "page")
                    if page_counter == 0:
                        await page.goto(url, wait_until="networkidle")
                    else:
                        await page.wait_for_load_state("networkidle")
                    page_counter += 1
                    raw = await page.evaluate(EXTRACT_SCRIPT)
                    label = self._slugify(target) or f"page_{page_counter}"
                    all_elements.extend(clean_elements(raw, label))

                elif action == "fill":
                    await self._fill_by_hint(page, step.get("field_hint", ""), step.get("value", ""))

                elif action == "click":
                    await self._click_by_hint(page, step.get("target_hint", ""))

            await browser.close()

        return all_elements

    @staticmethod
    def _slugify(text: str) -> str:
        return "_".join(text.lower().split())

    @staticmethod
    async def _fill_by_hint(page, field_hint: str, value: str) -> None:
        hint = field_hint.lower()
        candidates = await page.query_selector_all("input, textarea")
        for el in candidates:
            attrs = {
                "placeholder": (await el.get_attribute("placeholder")) or "",
                "name": (await el.get_attribute("name")) or "",
                "id": (await el.get_attribute("id")) or "",
                "aria-label": (await el.get_attribute("aria-label")) or "",
            }
            haystack = " ".join(attrs.values()).lower()
            if hint and hint in haystack:
                await el.fill(value)
                return

    @staticmethod
    async def _click_by_hint(page, target_hint: str) -> None:
        hint = target_hint.lower()
        candidates = await page.query_selector_all('button, a, input[type="submit"], [role="button"]')
        for el in candidates:
            text = ((await el.inner_text()) or (await el.get_attribute("value")) or "").strip().lower()
            if hint and (hint in text or text in hint):
                await el.click()
                return
