# Reads SNOWFLAKE_TOKEN from .env and writes it into ~/.dbt/profiles.yml

import pathlib
import re
import sys

ENV_FILE = pathlib.Path(__file__).parent.parent / ".env"
PROFILES_FILE = pathlib.Path.home() / ".dbt" / "profiles.yml"


def load_env_token(env_path: pathlib.Path) -> str:
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("SNOWFLAKE_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("SNOWFLAKE_TOKEN not found in .env")


def update_profiles(profiles_path: pathlib.Path, token: str) -> None:
    content = profiles_path.read_text()
    updated = re.sub(r"(token:\s*).*", f"\\1{token}", content)
    if updated == content:
        raise SystemExit("Could not find 'token:' line in profiles.yml — nothing changed.")
    profiles_path.write_text(updated)
    print(f"Updated {profiles_path}")


if __name__ == "__main__":
    token = load_env_token(ENV_FILE)
    print(f"Token read from .env: {token[:20]}...{token[-10:]}")
    update_profiles(PROFILES_FILE, token)
    print("Done. Run: uv run dbt debug --project-dir dbt")
