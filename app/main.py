from dotenv import load_dotenv

load_dotenv()

from .api import create_app  # noqa: E402


def create():
    """Entry point for: uvicorn app.main:create --factory"""
    return create_app()
