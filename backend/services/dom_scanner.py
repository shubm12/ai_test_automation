"""Stage 0 — DOM grounding.

Walks the real target app with Playwright, replaying a resolved flow (see
flow_resolver.py), and extracts every interactive AND informational element
with a ranked real selector: data-testid > id > name > class > text. This is
the anti-hallucination foundation for every later stage - the LLM is only
ever shown selectors that were actually observed on the live page.

The extraction net covers three structural (not site-specific) categories:
1. Interactive elements: button, a, input, select, textarea, [role="button"]
2. QA/accessibility conventions: data-testid/data-test/data-cy, ARIA live
   regions and alert/status roles - these are standards/conventions used
   across many sites, not guesses tied to any one site's markup.
3. Leaf text elements with a class (span/div/p/li/h1-h3 with no child
   elements): catches purely informational UI like counters, badges, and
   messages on any site, since "standalone text with a class" is a
   structural pattern rather than a keyword guess (e.g. "badge", "toast").
"""
from flows.definitions import FlowStep

EXTRACT_SCRIPT = """
() => {
    const interactive = document.querySelectorAll(
        'button, a, input, select, textarea, [role="button"]'
    );
    const informational = document.querySelectorAll(
        '[data-testid], [data-test], [data-cy], [aria-live], [role="alert"], [role="status"]'
    );
    const leafText = Array.from(
        document.querySelectorAll('span, div, p, li, h1, h2, h3')
    ).filter(el =>
        el.children.length === 0 &&
        el.className && typeof el.className === 'string' && el.className.trim() &&
        el.innerText && el.innerText.trim().length > 0 && el.innerText.trim().length <= 80
    );

    const seen = new Set();
    const nodes = [];
    [...interactive, ...informational, ...leafText].forEach(el => {
        if (!seen.has(el)) {
            seen.add(el);
            nodes.push(el);
        }
    });

    const out = [];
    nodes.forEach(el => {
        out.push({
            tag: el.tagName.toLowerCase(),
            text: (el.innerText || el.value || '').trim(),
            id: el.id || null,
            testAttr: ['data-testid', 'data-test', 'data-cy'].find(a => el.getAttribute(a)) || null,
            testId: el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('data-cy'),
            name: el.getAttribute('name'),
            type: el.type || null,
            placeholder: el.getAttribute('placeholder'),
            ariaLabel: el.getAttribute('aria-label'),
            className: (typeof el.className === 'string' && el.className.trim()) || null
        });
    });
    return out;
}
"""


def rank_selector(el: dict) -> str | None:
    if el.get("testId"):
        # Emit the selector with the exact attribute the value was observed on
        # (data-testid vs data-test vs data-cy) - advertising a data-test value
        # as [data-testid=...] produces a selector that matches nothing.
        attr = el.get("testAttr") or "data-testid"
        return f'[{attr}="{el["testId"]}"]'
    if el.get("id"):
        return f'#{el["id"]}'
    if el.get("name"):
        return f'[name="{el["name"]}"]'
    if el.get("className"):
        first_class = el["className"].split()[0]
        if first_class:
            return f'.{first_class}'
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
    async def scan(self, url: str, flow_steps: list[FlowStep]) -> tuple[list[dict], list[str]]:
        """Returns (element_map, warnings).

        Warnings record every flow step whose hint matched nothing on the live
        page. A silently skipped step means the browser never reached the state
        the remaining steps assume, so pages past that point were likely never
        scanned - the warning makes that visible to the API caller instead of
        letting a stalled scan masquerade as a complete one.
        """
        from playwright.async_api import async_playwright

        all_elements: list[dict] = []
        warnings: list[str] = []
        seen_selectors: set[str] = set()
        page_counter = 0
        current_label = "landing_page"

        def _record(raw: list[dict], label: str) -> None:
            for el in clean_elements(raw, label):
                selector = el["recommended_selector"]
                if selector not in seen_selectors:
                    seen_selectors.add(selector)
                    all_elements.append(el)

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
                    current_label = self._slugify(target) or f"page_{page_counter}"
                    raw = await page.evaluate(EXTRACT_SCRIPT)
                    _record(raw, current_label)

                elif action == "fill":
                    hint = step.get("field_hint", "")
                    filled = await self._fill_by_hint(page, hint, step.get("value", ""))
                    if not filled:
                        warnings.append(
                            f"fill '{hint}' matched no input on '{current_label}' - "
                            "this step was skipped; later pages may not have been scanned"
                        )

                elif action == "click":
                    hint = step.get("target_hint", "")
                    clicked = await self._click_by_hint(page, hint)
                    if not clicked:
                        warnings.append(
                            f"click '{hint}' matched no element on '{current_label}' - "
                            "this step was skipped; later pages may not have been scanned"
                        )
                        continue
                    # Clicks change DOM state (badges, toggled buttons, toasts) without
                    # necessarily triggering a "navigate" step in the resolved flow - a
                    # click on a single-page app rarely changes the URL, so the LLM-derived
                    # flow has no reason to emit a matching navigate. Re-scan unconditionally
                    # so that state is still grounded rather than silently missed.
                    try:
                        await page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        pass
                    raw = await page.evaluate(EXTRACT_SCRIPT)
                    _record(raw, f"{current_label}_after_{self._slugify(hint or 'click')}")

            await browser.close()

        return all_elements, warnings

    @staticmethod
    def _slugify(text: str) -> str:
        return "_".join(text.lower().split())

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase and strip non-alphanumerics so 'First Name', 'first-name'
        and 'firstName' all compare equal."""
        return "".join(ch for ch in text.lower() if ch.isalnum())

    @classmethod
    async def _fill_by_hint(cls, page, field_hint: str, value: str) -> bool:
        hint = cls._normalize(field_hint)
        if not hint:
            return False
        candidates = await page.query_selector_all("input, textarea")
        for el in candidates:
            attrs = [
                (await el.get_attribute("placeholder")) or "",
                (await el.get_attribute("name")) or "",
                (await el.get_attribute("id")) or "",
                (await el.get_attribute("aria-label")) or "",
                (await el.get_attribute("data-test")) or "",
                (await el.get_attribute("data-testid")) or "",
            ]
            haystack = cls._normalize(" ".join(attrs))
            if hint in haystack:
                # Hidden/disabled fields can match by attributes; skip them and
                # keep looking instead of hanging on an uninteractable element.
                if not await el.is_visible():
                    continue
                try:
                    await el.fill(value, timeout=3000)
                    return True
                except Exception:
                    continue
        return False

    @classmethod
    async def _click_by_hint(cls, page, target_hint: str) -> bool:
        # Words like "button"/"link" describe the element kind, not its label -
        # "checkout button" must match a button whose text is just "Checkout".
        hint = cls._normalize(
            " ".join(
                w for w in target_hint.lower().split() if w not in ("button", "link", "icon", "the", "a", "an")
            )
        )
        if not hint:
            return False
        candidates = await page.query_selector_all('button, a, input[type="submit"], [role="button"]')
        for el in candidates:
            text = cls._normalize(
                ((await el.inner_text()) or (await el.get_attribute("value")) or "").strip()
            )
            attr_ids = cls._normalize(
                " ".join(
                    [
                        (await el.get_attribute("id")) or "",
                        (await el.get_attribute("data-test")) or "",
                        (await el.get_attribute("data-testid")) or "",
                        (await el.get_attribute("aria-label")) or "",
                    ]
                )
            )
            if (text and (hint in text or text in hint)) or (attr_ids and hint in attr_ids):
                # Attribute matching can hit elements that exist in the DOM but
                # aren't visible (e.g. a hidden menu's close button). Skip those
                # and keep looking; a short timeout caps the cost of an element
                # that is visible but not clickable, rather than crashing the
                # whole scan after Playwright's 30s default.
                if not await el.is_visible():
                    continue
                try:
                    await el.click(timeout=3000)
                    return True
                except Exception:
                    continue
        return False
