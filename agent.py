from typing import Annotated, Sequence
from dotenv import load_dotenv
import os
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import (
    BaseMessage,
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph
from pydantic import BaseModel
from langgraph.graph.message import add_messages
from tools.run_unit_tests_tool import run_unit_tests
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# import sqlite3
# import aiosqlite


class AgentState(BaseModel):
    """
    Persistent agent state tracked across the graph.
    - messages: complete chat history (system + user + assistant + tool messages)
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]


class Agent:
    def __init__(self):
        self._initialized = False
        # Load environment
        load_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing ANTHROPIC_API_KEY in environment. Set it in .env or your shell."
            )

        # Model instantiation (Claude Sonnet latest)
        self.model = ChatAnthropic(
            model="claude-3-7-sonnet-latest",
            temperature=0.3,
            max_tokens=4096,
            api_key=api_key,
        )

        # Rich console for UI
        self.console = Console()

        # Build workflow graph
        self.workflow = StateGraph(AgentState)

        # Register nodes
        self.workflow.add_node("user_input", self.user_input)
        self.workflow.add_node("model_response", self.model_response)
        self.workflow.add_node("tool_use", self.tool_use)

        # Edges: start at user_input
        self.workflow.set_entry_point("user_input")
        self.workflow.add_edge("user_input", "model_response")
        self.workflow.add_edge("tool_use", "model_response")

        # Conditional: model_response -> tool_use OR -> user_input
        self.workflow.add_conditional_edges(
            "model_response",
            self.check_tool_use,
            {
                "tool_use": "tool_use",
                "user_input": "user_input",
            },
        )

    async def initialize(self):
        """Async initialization - load tools and other async resources"""
        if self._initialized:
            return self

        print("🔄 Initializing agent...")

        # Tools
        local_tools = [run_unit_tests]

        # Set up MCP client
        mcp_tools = await self.get_mcp_tools()
        self.tools = local_tools + mcp_tools
        print(
            f"✅ Loaded {len(self.tools)} total tools (Local: {len(local_tools)} + MCP: {len(mcp_tools)})"
        )
        self._initialized = True

        # Bind tools to model
        self.model_with_tools = self.model.bind_tools(self.tools)

        # Compile graph
        async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as memory:
            self.agent = self.workflow.compile(checkpointer=memory)
        # Compile graph: enter AsyncSqliteSaver once and keep it open for agent lifetime
        # (prevents re-opening/closing aiosqlite threads repeatedly)
        db_path = os.path.join(os.getcwd(), "checkpoints.db")
        self._checkpointer_ctx = AsyncSqliteSaver.from_conn_string(db_path)
        self.checkpointer = await self._checkpointer_ctx.__aenter__()
        self.agent = self.workflow.compile(checkpointer=self.checkpointer)

        # Optional: print a greeting panel
        self.console.print(
            Panel.fit(
                Markdown("**LangGraph Coding Agent** — Claude Code Clone"),
                title="[bold green]Ready[/bold green]",
                border_style="green",
            )
        )
        return self

    async def run(self):
        """
        Main loop: invoke the workflow repeatedly, never exits automatically.
        """
        config = {"configurable": {"thread_id": "1"}}
        return await self.agent.ainvoke(
            {"messages": AIMessage(content="What can I do for you?")}, config=config
        )

    async def close_checkpointer(self):
        """Close the async checkpointer context if opened."""
        if hasattr(self, "_checkpointer_ctx"):
            await self._checkpointer_ctx.__aexit__(None, None, None)

    async def get_mcp_tools(self):
        from langchain_mcp_adapters.client import MultiServerMCPClient

        GITHUB_PERSONAL_ACCESS_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
        mcp_client = MultiServerMCPClient(
            {
                "Run_Python_MCP": {
                    "command": "docker",
                    "args": [
                        "run",
                        "-i",
                        "--rm",
                        "deno-docker:latest",  # image name
                        "deno",  # the command inside container
                        "run",
                        "-N",
                        "-R=node_modules",
                        "-W=node_modules",
                        "--node-modules-dir=auto",
                        "jsr:@pydantic/mcp-run-python",
                        "stdio",
                    ],
                    "transport": "stdio",
                },
                "duckduckgo_MCP": {
                    "command": "docker",
                    "args": ["run", "-i", "--rm", "mcp/duckduckgo"],
                    "transport": "stdio",
                },
                "desktop_commander_in_docker_MCP": {
                    "command": "docker",
                    "args": [
                        "run",
                        "-i",
                        "--rm",
                        "-v",
                        "/Users/lorreatlan/Documents/MyPlayDocuments:/mnt/documents",
                        "mcp/desktop-commander:latest",
                    ],
                    "transport": "stdio",
                },
                "Github_MCP": {
                    "command": "docker",
                    "args": [
                        "run",
                        "-i",
                        "--rm",
                        "-e",
                        f"GITHUB_PERSONAL_ACCESS_TOKEN={GITHUB_PERSONAL_ACCESS_TOKEN}",
                        "-e",
                        "GITHUB_READ-ONLY=1",
                        "ghcr.io/github/github-mcp-server",
                    ],
                    "transport": "stdio",
                },
            }
        )
        mcp_tools = await mcp_client.get_tools()
        for tb in mcp_tools:
            print(f"MCP 🔧 {tb.name}")
        return mcp_tools

    # Node: user_input
    def user_input(self, state: AgentState) -> AgentState:
        """
        Ask user for input and append HumanMessage to state.
        """
        self.console.print("[bold cyan]User Input[/bold cyan]: ")
        user_input = self.console.input("> ")
        return {"messages": [HumanMessage(content=user_input)]}

    # Node: model_response
    def model_response(self, state: AgentState) -> AgentState:
        """
        Call the LLM (with tools bound). Print assistant content and any tool_call previews.
        Decide routing via check_tool_use.
        """
        system_text = """You are a specialised agent for maintaining and developing codebases.
            ## Development Guidelines:

            1. **Test Failures:**
            - When tests fail, fix the implementation first, not the tests.
            - Tests represent expected behavior; implementation should conform to tests
            - Only modify tests if they clearly don't match specifications

            2. **Code Changes:**
            - Make the smallest possible changes to fix issues
            - Focus on fixing the specific problem rather than rewriting large portions
            - Add unit tests for all new functionality before implementing it

            3. **Best Practices:**
            - Keep functions small with a single responsibility
            - Implement proper error handling with appropriate exceptions
            - Be mindful of configuration dependencies in tests

            Ask for clarification when needed. Remember to examine test failure messages carefully to understand the root cause before making any changes."""
        # Compose messages: include prior state
        messages = [
            SystemMessage(
                content=[
                    {
                        "type": "text",
                        "text": system_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            ),
            HumanMessage(content=f"Working directory: {os.getcwd()}"),
        ] + state.messages

        # Invoke model
        response = self.model_with_tools.invoke(messages)
        if isinstance(response.content, list):
            for item in response.content:
                if item["type"] == "text":
                    text = item.get("text", "")
                    if text:
                        self.console.print(
                            Panel.fit(
                                Markdown(text),
                                title="[magenta]Assistant[/magenta]",
                                border_style="magenta",
                            )
                        )
                elif item["type"] == "tool_use":
                    self.console.print(
                        Panel.fit(
                            Markdown(
                                f"{item["name"]} with args {item.get("args",None)}"
                            ),
                            title="Tool Use",
                        )
                    )
        else:
            self.console.print(
                Panel.fit(
                    Markdown(response.content),
                    title="[magenta]Assistant[/magenta]",
                )
            )

        return {"messages": [response]}

    # Conditional router
    def check_tool_use(self, state: AgentState) -> str:
        """
        If the last assistant message has tool_calls, route to 'tool_use', else route to 'user_input'.
        """
        if state.messages[-1].tool_calls:
            return "tool_use"
        return "user_input"

    # Node: tool_use
    async def tool_use(self, state: AgentState) -> AgentState:
        """
        Execute tool calls from the last assistant message and return ToolMessage(s),
        preserving tool_call_id so the model can reconcile results when we go back to model_response.
        """
        from langgraph.prebuilt import ToolNode

        response = []
        tools_by_name = {t.name: t for t in self.tools}

        for tc in state.messages[-1].tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            print(f"🔧 Invoking tool '{tool_name}' with args {tool_args}")
            tool = tools_by_name.get(tool_name)
            print(f"🛠️ Found tool: {tool}")
            tool_node = ToolNode([tool])

            # response = interrupt(
            #     {
            #         "action": "review_tool_call",
            #         "tool_name": tool_name,
            #         "tool_input": state["messages"][-1].content,
            #         "message": "Approve this tool call?",
            #     }
            # )
            # # Handle the response after the interrupt (e.g., resume or modify)
            # if response == "approved":
            try:
                tool_result = await tool_node.ainvoke(state)
                print(f"🛠️ Tool Result: {tool_result}")
                response.append(tool_result["messages"][0])
                self.console.print(
                    Panel.fit(
                        Syntax(
                            "\n" + tool_result["messages"][0].content + "\n", "text"
                        ),
                        title="Tool Result",
                    )
                )
            except Exception as e:
                response.append(
                    ToolMessage(
                        content=f"ERROR: Exception during tool '{tool_name}' execution: {e}",
                        tool_call_id=tc["id"],
                    )
                )
                self.console.print(
                    Panel.fit(
                        Markdown(
                            f"**ERROR**: Exception during tool '{tool_name}' execution: {e}"
                        ),
                        title="Tool Error",
                        border_style="red",
                    )
                )
            # else:
            #     # Handle rejection or modification
            #     pass
        return {"messages": response}

    def print_mermaid_workflow(self):
        """
        Utility: print Mermaid diagram to visualize the graph edges.
        """
        try:
            mermaid = self.agent.get_graph().draw_mermaid_png(
                output_file_path="langgraph_workflow.png",
                max_retries=5,
                retry_delay=2,
            )
        except Exception as e:
            print(f"Error generating mermaid PNG: {e}")
            mermaid = self.agent.get_graph().draw_mermaid()
            self.console.print(
                Panel.fit(
                    Syntax(mermaid, "mermaid", theme="monokai", line_numbers=False),
                    title="Workflow (Mermaid)",
                    border_style="cyan",
                )
            )
            print(self.agent.get_graph().draw_ascii())
