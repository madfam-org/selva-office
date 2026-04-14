import json
import subprocess
import os

MCP_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp_config.json")


class ACPAnalystNode:
    """
    Phase I: The Analyst (Dirty Environment).

    Uses Zero-Context RPC subprocess threads to scrape target URLs cheaply,
    dropping the heavy Playwright/graph-state overhead. When ``mcp_config.json``
    is present, the subagent bootstraps the configured MCP servers first,
    giving it dynamic access to external tools (Tavily search, GitHub, etc.)
    without requiring container rebuilds — exactly mirroring the Hermes Agent
    Model Context Protocol pattern.
    """

    def __init__(self, target_url: str) -> None:
        self.target_url = target_url

    # ------------------------------------------------------------------
    # MCP bootstrap
    # ------------------------------------------------------------------

    def _get_mcp_bootstrap_snippet(self) -> str:
        """
        Return a Python code snippet that starts the MCP server processes
        listed in ``mcp_config.json``.  The snippet is injected at the top
        of the RPC child-script so tool servers are available before crawling.
        """
        try:
            config_path = os.path.abspath(MCP_CONFIG_PATH)
            with open(config_path) as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return "# MCP config not found — running without external tools\n"

        lines = [
            "import subprocess as _sp, os as _os",
            "_mcp_procs = []",
        ]
        for name, srv in config.get("mcpServers", {}).items():
            cmd = json.dumps([srv["command"]] + srv.get("args", []))
            env_overrides = srv.get("env", {})
            env_str = "{**_os.environ, " + ", ".join(
                f'"{k}": _os.environ.get("{k}", "")' for k in env_overrides
            ) + "}"
            lines.append(
                f'_mcp_procs.append(_sp.Popen({cmd}, env={env_str}, '
                f'stdout=_sp.DEVNULL, stderr=_sp.DEVNULL))  # {name}'
            )
        lines.append("import time; time.sleep(1)  # give servers a moment to start")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Core extraction
    # ------------------------------------------------------------------

    def run(self) -> dict:
        print(f"[Phase I] Launching RPC subagent (with MCP) for {self.target_url} …")

        mcp_bootstrap = self._get_mcp_bootstrap_snippet()
        extracted_text = ""

        crawler_script = f"""\
{mcp_bootstrap}
import requests
try:
    resp = requests.get('{self.target_url}', timeout=10, headers={{"User-Agent": "AutoSwarm-Analyst/1.0"}})
    print(resp.text[:1000])
except Exception as e:
    print(f"Error fetching: {{e}}")
finally:
    for p in _mcp_procs:
        p.terminate()
"""
        try:
            result = subprocess.run(
                ["python", "-c", crawler_script],
                capture_output=True,
                text=True,
                timeout=30,
            )
            extracted_text = result.stdout.strip()
            if result.returncode != 0 and result.stderr:
                print(f"[Phase I] Subagent stderr: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            extracted_text = "RPC subagent timed out."
        except Exception as e:
            extracted_text = f"Error capturing page via RPC: {e}"

        # Pseudocode: We would normally pass `extracted_text` to an LLM chain to structure the PRD
        # prd_json = llm_chain.invoke({"source_text": extracted_text})
        
        return {
            "prd": f"# PRD Draft for {self.target_url}\n\n## Extracted Context\n...{extracted_text[:500]}...",
            "tests": "def test_login():\n    assert True"
        }
