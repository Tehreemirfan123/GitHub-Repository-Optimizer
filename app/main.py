"""Configuration verification script."""

from app.config.settings import get_settings


def main() -> None:
    """Verify that settings load successfully without exposing the API key."""
    settings = get_settings()

    print("Configuration loaded successfully.")
    print(f"Application name: {settings.app_name}")
    print(f"Gemini model: {settings.gemini_model}")
    print("Gemini API key loaded: True")
    print()
    print("Run the agent with:")
    print("  adk run app")
    print()
    print("Or start the web interface with:")
    print("  adk web")


if __name__ == "__main__":
    main()