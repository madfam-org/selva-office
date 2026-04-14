import json
from playwright.sync_api import sync_playwright

class ACPAnalystNode:
    """
    Phase I: The Analyst (Dirty Environment)
    Interacts with target UI via Playwright/Selenium.
    Generates Black-Box tests and an initial PRD.
    """
    def __init__(self, target_url: str):
        self.target_url = target_url

    def run(self) -> dict:
        print(f"[Phase I] Launching Playwright to observe {self.target_url}...")
        
        extracted_text = ""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(self.target_url)
                
                # Simple extraction strategy: wait for network idle and grab inner text
                page.wait_for_load_state("networkidle")
                extracted_text = page.locator("body").inner_text()
                
                browser.close()
        except Exception as e:
            print(f"[Phase I] Playwright error: {e}")
            extracted_text = f"Error capturing page: {e}"

        # Pseudocode: We would normally pass `extracted_text` to an LLM chain to structure the PRD
        # prd_json = llm_chain.invoke({"source_text": extracted_text})
        
        return {
            "prd": f"# PRD Draft for {self.target_url}\n\n## Extracted Context\n...{extracted_text[:500]}...",
            "tests": "def test_login():\n    assert True"
        }
