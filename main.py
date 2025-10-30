from agent import Agent
import asyncio


async def async_main():
    agent = Agent()
    await agent.initialize()
    agent.print_mermaid_workflow()
    await agent.run()
    await agent.close_checkpointer()


if __name__ == "__main__":
    asyncio.run(async_main())
