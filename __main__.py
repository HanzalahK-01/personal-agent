"""Entry point for personal AI agent system."""

import asyncio
import sys
from dotenv import load_dotenv

load_dotenv()

try:
    from bot.main import main
except ImportError as e:
    print(f"Error: Failed to import bot module: {e}")
    print("Make sure all dependencies are installed: pip install -r requirements.txt")
    sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
