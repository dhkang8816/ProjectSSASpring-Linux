import os
import secrets
from apps import runtime_settings

def sqlite_database_uri(name, *, testing=False):
    """Require an existing DB; tests without a file use an in-memory store."""
    configured = os.getenv(name, "").strip()
    if not configured and testing:
        return "sqlite:///:memory:"
    path = runtime_settings.readable_file(name, configured)
    if not os.access(path, os.W_OK) or not os.access(path.parent, os.W_OK | os.X_OK):
        raise runtime_settings.RuntimePathError(f"{name} and its parent must allow SQLite writes")
    return f"sqlite:///{path.as_posix()}"


def _secret(name, fallback=None):
    """Read deployment secrets without committing a reusable fallback value."""
    value = os.getenv(name, "").strip()
    return value or fallback or secrets.token_urlsafe(32)

# BaseConfig 클래스를 작성한다
class BaseConfig:
    SECRET_KEY = _secret("SSA_FLASK_SECRET_KEY")
    WTF_CSRF_SECRET_KEY = _secret("SSA_FLASK_CSRF_SECRET_KEY", SECRET_KEY)


# BaseConfig 클래스를 상속하여 LocalConfig 클래스를 작성한다
class LocalConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = None
    SQLALCHEMY_TRACK_MODIFICATIONS=False
    SQLALCHEMY_ECHO=False

    @classmethod
    def database_uri(cls):
        return sqlite_database_uri("SSA_SQLITE_PATH")


# BaseConfig 클래스를 상속하여 TestingConfig 클래스를 작성한다
class TestingConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False

    @classmethod
    def database_uri(cls):
        return sqlite_database_uri("SSA_TEST_SQLITE_PATH", testing=True)
    
# config 사전에 매핑한다
config = {
    "testing": TestingConfig,
    "local": LocalConfig,
}


