"""Configuration management for Dhan Tracker."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

# Project root directory (where main.py is located)
# config.py -> dhan_tracker -> src -> dhan-tracker (project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Config file locations (in order of priority)
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"
HOME_CONFIG_DIR = Path.home() / ".dhan-tracker"
HOME_CONFIG_FILE = HOME_CONFIG_DIR / "config.env"

logger = logging.getLogger(__name__)


def get_config_file() -> Path | None:
    """Get the first available config file."""
    # Priority: project .env > home config
    if PROJECT_ENV_FILE.exists():
        return PROJECT_ENV_FILE
    if HOME_CONFIG_FILE.exists():
        return HOME_CONFIG_FILE
    return None


def _has_required_env_vars() -> bool:
    """Check if required environment variables are already set."""
    return bool(os.getenv("DHAN_ACCESS_TOKEN") and os.getenv("DHAN_CLIENT_ID"))


def _try_load_token_from_db() -> str | None:
    """Try to load the Dhan access token from the database."""
    try:
        from dhan_tracker.database import get_dhan_token, is_database_available

        if not is_database_available():
            return None

        token = get_dhan_token()
        if token:
            logger.info("Loaded access token from database")
            return token
    except Exception as e:
        logger.debug(f"Could not load token from database: {e}")

    return None


@dataclass
class DhanConfig:
    """Dhan API configuration."""

    access_token: str
    client_id: str
    base_url: str = "https://api.dhan.co/v2"

    # Stop loss configuration (percentage below current price)
    default_stop_loss_percent: float = 5.0

    @classmethod
    def from_env(cls) -> "DhanConfig":
        """Load configuration from environment variables."""
        access_token = os.getenv("DHAN_ACCESS_TOKEN")
        client_id = os.getenv("DHAN_CLIENT_ID")

        if not access_token:
            raise ValueError(
                "DHAN_ACCESS_TOKEN environment variable is required")
        if not client_id:
            raise ValueError("DHAN_CLIENT_ID environment variable is required")

        stop_loss_percent = float(os.getenv("DHAN_STOP_LOSS_PERCENT", "5.0"))

        return cls(
            access_token=access_token,
            client_id=client_id,
            default_stop_loss_percent=stop_loss_percent,
        )

    @classmethod
    def load(cls) -> "DhanConfig":
        """Load configuration from database, environment variables, or .env file.

        This is the preferred method for loading config. Priority:
        1. Database (for refreshed tokens that persist across restarts)
        2. Environment variables (Azure App Service settings)
        3. .env file (local development)
        """
        client_id = os.getenv("DHAN_CLIENT_ID")

        # Try loading token from database first (persisted refreshed tokens)
        db_token = _try_load_token_from_db()
        if db_token and client_id:
            stop_loss_percent = float(
                os.getenv("DHAN_STOP_LOSS_PERCENT", "5.0"))
            return cls(
                access_token=db_token,
                client_id=client_id,
                default_stop_loss_percent=stop_loss_percent,
            )

        # Fall back to env vars
        if _has_required_env_vars():
            return cls.from_env()

        # Finally, try to load from .env file
        return cls.from_file()

    @classmethod
    def from_file(cls, filepath: Path | None = None) -> "DhanConfig":
        """Load configuration from a .env file."""
        if filepath is None:
            filepath = get_config_file()

        if filepath is None or not filepath.exists():
            raise FileNotFoundError(
                f"Config file not found.\n"
                f"Please create .env in project folder or run 'python main.py init'\n"
                f"Expected locations:\n"
                f"  - {PROJECT_ENV_FILE}\n"
                f"  - {HOME_CONFIG_FILE}"
            )

        # Parse simple .env file
        config_vars = {}
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    config_vars[key.strip()] = value.strip().strip(
                        '"').strip("'")

        # Set environment variables
        for key, value in config_vars.items():
            os.environ[key] = value

        return cls.from_env()


def create_sample_config(in_project: bool = True) -> Path:
    """Create a sample config file.

    Args:
        in_project: If True, create .env in project folder. Otherwise, create in home dir.

    Returns:
        Path to the created config file.
    """
    sample_content = """# Dhan Tracker Configuration
# Get your access token from https://web.dhan.co -> My Profile -> Access DhanHQ APIs

DHAN_ACCESS_TOKEN=your_access_token_here
DHAN_CLIENT_ID=your_client_id_here

# Stop loss percentage (default: 5%)
DHAN_STOP_LOSS_PERCENT=5.0

# App password for UI and API access (required)
APP_PASSWORD=your_secure_password_here
"""

    if in_project:
        config_file = PROJECT_ENV_FILE
    else:
        HOME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config_file = HOME_CONFIG_FILE

    if not config_file.exists():
        with open(config_file, "w") as f:
            f.write(sample_content)
        print(f"Sample config created at: {config_file}")

    return config_file
