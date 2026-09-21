from django.shortcuts import render
from django.http import Http404
from django.db.models import Count
from django.core.cache import cache

from ..models import Package, ManPage, SymbolicLink, UpdateLog

# make views available from the main "views" package
from .listing import listing
from .man_page import man_page
from .search import search

def get_homepage_stats():
    # Attempt to read pre-computed stats from the latest UpdateLog
    latest_log = UpdateLog.objects.order_by("-id").first()
    if latest_log and latest_log.stats_count_man_pages is not None:
        count_man_pages = latest_log.stats_count_man_pages
        count_symlinks = latest_log.stats_count_symlinks
        count_all_pkgs = latest_log.stats_count_all_pkgs
        count_pkgs_with_mans = latest_log.stats_count_pkgs_with_mans or 0
    else:
        count_man_pages = ManPage.objects.count()
        count_symlinks = SymbolicLink.objects.count()
        count_all_pkgs = Package.objects.count()
        count_pkgs_with_mans = ManPage.objects.aggregate(Count("package_id", distinct=True))["package_id__count"] or 0

    return {
        "count_man_pages": count_man_pages,
        "count_symlinks": count_symlinks,
        "count_pkgs_with_mans": count_pkgs_with_mans,
        "count_pkgs_without_mans": max(0, count_all_pkgs - count_pkgs_with_mans),
    }

def index(request):
    stats = cache.get_or_set("homepage:stats", get_homepage_stats, timeout=3600)
    last_updates = UpdateLog.objects.order_by("-id")[:5]
    context = {
        **stats,
        "last_updates": last_updates,
        "search_autofocus": True,
    }
    return render(request, "index.html", context)
