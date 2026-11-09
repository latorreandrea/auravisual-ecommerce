"""Shared pagination helpers for the catalogue and the workspace lists.

Both views paginate at the database level (``LIMIT``/``OFFSET`` plus a single
``COUNT``) so a growing table never turns into a full scan per request. The
template needs ``page_obj``, ``page_links``, ``is_paginated`` and
``pagination_query``, which the ``partials/pagination.html`` partial renders.
"""

from django.core.paginator import Paginator


def _pagination_query(request):
    """Return the filters of the current request, ready to prefix a page link.

    The catalogue adds ``?status=`` for staff, so every page link has to keep the
    active filters; without filters this returns an empty string and the links
    stay a plain ``?page=N``.
    """

    params = request.GET.copy()
    params.pop("page", None)
    query = params.urlencode()
    return f"{query}&" if query else ""


def paginate(request, queryset, per_page):
    """Return ``(page_obj, context)`` for the requested ``?page=`` value.

    ``Paginator.get_page`` validates the raw value: a missing or non-numeric page
    falls back to the first page and a page past the end to the last one, so old
    bookmarks and crawlers never see an ``Http404``. Zero and negative numbers are
    clamped to the first page here, because Django would otherwise send them to
    the last page (``EmptyPage`` semantics).
    """

    raw_page = request.GET.get("page")
    try:
        if raw_page is not None and int(raw_page) < 1:
            raw_page = 1
    except (TypeError, ValueError):
        pass

    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(raw_page)

    page_links = []
    for number in paginator.get_elided_page_range(page_obj.number):
        if number == paginator.ELLIPSIS:
            page_links.append({"is_ellipsis": True})
        else:
            page_links.append(
                {
                    "number": number,
                    "is_ellipsis": False,
                    "is_current": number == page_obj.number,
                }
            )

    return page_obj, {
        "page_obj": page_obj,
        "page_links": page_links,
        "is_paginated": paginator.num_pages > 1,
        "pagination_query": _pagination_query(request),
    }
