import subprocess
from langchain.tools import tool


@tool
def run_unit_tests() -> str:
    """Run unit tests using uv."""
    result = subprocess.run(
        ["uv", "run", "pytest", "-xvs", "tests/"], capture_output=True, text=True
    )
    return result.stdout
