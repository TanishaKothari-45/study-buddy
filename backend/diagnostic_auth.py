from app.core.config import settings
import os
from pathlib import Path

import datetime

print(f"Current UTC Time: {datetime.datetime.utcnow()}")
print(f"Current Local Time: {datetime.datetime.now()}")
print(f"Project Name: {settings.PROJECT_NAME}")
print(f"Access Token Expire Minutes: {settings.ACCESS_TOKEN_EXPIRE_MINUTES} ({settings.ACCESS_TOKEN_EXPIRE_MINUTES/60} hours)")
print(f"JWT Algorithm: {settings.JWT_ALGORITHM}")
print(f"JWT Secret Key Length: {len(settings.JWT_SECRET_KEY) if settings.JWT_SECRET_KEY else 0}")
print(f"Encryption Key Length: {len(settings.ENCRYPTION_KEY) if settings.ENCRYPTION_KEY else 0}")
print(f"Encryption Key Source: {'Environment/.env' if os.getenv('ENCRYPTION_KEY') else 'Auto-generated (Temporary!)'}")
print(f"Current Directory: {os.getcwd()}")
print(f"Base Directory: {settings.BASE_DIR}")

env_path = Path(".env")
print(f".env in CWD exists: {env_path.exists()}")
if env_path.exists():
    print(f".env size: {env_path.stat().st_size} bytes")

project_root = Path(__file__).resolve().parent.parent
root_env = project_root / ".env"
print(f".env in project root ({project_root}) exists: {root_env.exists()}")
