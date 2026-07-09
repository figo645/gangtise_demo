import os

from src.runtime import app
from src.domain.core_services import startup_bootstrap
import src.app_setup  # noqa: F401


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5001"))
    debug = os.environ.get("DEBUG", "1").lower() in {"1", "true", "yes", "y"}
    startup_bootstrap()
    app.run(host=host, port=port, debug=debug)
