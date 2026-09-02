"""Production WSGI entry point.

Gunicorn preloads this module in its master process.  Shared schema/default
bootstrap happens exactly once and background loops are intentionally absent;
they run in the dedicated Worker and Scheduler processes.
"""

from app import app
