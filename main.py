from __future__ import annotations

import asyncio
from pathlib import Path

from cogito_agent.cli.app import CogitoCLI


async def async_main() -> None:
    app = CogitoCLI(workspace=Path("workspace"))
    await app.run()


if __name__ == "__main__":
    asyncio.run(async_main())
