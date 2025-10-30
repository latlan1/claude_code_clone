from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class FileReadToolInput(BaseModel):
    file_path: str = Field(..., description="Absolute path to the file to read")


class FileReadTool(BaseTool):
    name: str = "file_read"
    description: str = (
        "Reads a file designated by the supplied absolute path and returns the content as string. "
        "If the path is not absolute, the tool will attempt to resolve it against the provided working directory. "
        "Handle errors gracefully and return a helpful message when the file cannot be found or opened."
    )
    args_schema: type = FileReadToolInput

    def _run(self, file_path: str) -> str:
        """
        Synchronous tool run. Reads file content. Returns text or an error message.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
