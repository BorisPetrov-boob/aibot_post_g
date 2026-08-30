"""One-time interactive Telethon login to create the .session file.

Run locally (not in Docker):  python scripts/telethon_login.py
"""
import asyncio

from app.telegram.bot import interactive_login

if __name__ == "__main__":
    asyncio.run(interactive_login())
