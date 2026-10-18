"""Small background-task facade for deferred print generation.

The local implementation uses a thread pool so the project stays dependency
free. In production replace ``_executor`` with Celery/RQ and keep the same
``dispatch_print_generation`` entry point.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="customization-print")


def _run(draft_id):
    close_old_connections()
    try:
        from .models import CustomizationDraft
        from .services.printing import generate_print_file

        draft = CustomizationDraft.objects.select_related("product").get(pk=draft_id)
        generate_print_file(draft)
    except Exception:
        logger.exception("Could not generate the print file for draft %s", draft_id)
    finally:
        close_old_connections()


def dispatch_print_generation(draft_ids):
    ids = [str(draft_id) for draft_id in draft_ids]
    if not ids:
        return

    if settings.CUSTOMIZATION_PRINT_ASYNC:
        for draft_id in ids:
            transaction.on_commit(
                lambda value=draft_id: _executor.submit(_run, value)
            )
    else:
        for draft_id in ids:
            _run(draft_id)
