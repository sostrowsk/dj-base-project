"""Smoke tests for the in-tree base_project app extraction (W18-BP1).

Covers: module imports, leasing shim identity, deprecation warnings,
templatetag library registration, template resolution/rendering,
static file resolution and middleware/asgi wiring.
"""

import importlib
import warnings
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.backends.django import get_installed_libraries
from django.template.loader import get_template, render_to_string
from django.test import SimpleTestCase

MOVED_TEMPLATES = [
    "_pagination.html",
    "_empty.html",
    "empty.html",
    "base_container.html",
    "base_container_fluid.html",
    "base_form.html",
    "_message.html",
    "_breadcrumb.html",
]


class BaseProjectModuleImportTests(SimpleTestCase):
    def test_core_modules_import(self):
        import base_project.middleware_coop  # noqa: F401
        import base_project.middleware_db  # noqa: F401
        import base_project.redis_client  # noqa: F401
        import base_project.redis_lock  # noqa: F401
        import base_project.retry_utils  # noqa: F401

    def test_app_is_installed_at_end(self):
        assert settings.INSTALLED_APPS[-1] == "base_project.apps.BaseProjectConfig"


class LeasingShimIdentityTests(SimpleTestCase):
    def test_redis_client_shim_reexports_same_objects(self):
        import base_project.redis_client as new
        import leasing.redis_client as shim

        assert shim.RedisClient is new.RedisClient
        assert shim.get_redis_client_from_env is new.get_redis_client_from_env
        assert shim.redis_breaker is new.redis_breaker
        assert shim.DEFAULT_MAX_RETRIES == new.DEFAULT_MAX_RETRIES

    def test_retry_utils_shim_reexports_same_objects(self):
        import base_project.retry_utils as new
        import leasing.retry_utils as shim

        assert shim.RetryStrategy is new.RetryStrategy
        assert shim.retry_with_backoff is new.retry_with_backoff

    def test_redis_lock_shim_reexports_same_objects(self):
        import base_project.redis_lock as new
        import leasing.utils.redis_lock as shim

        assert shim.RedisLock is new.RedisLock
        assert shim.AutoRenewingRedisLock is new.AutoRenewingRedisLock
        assert shim.distributed_task is new.distributed_task

    def test_redis_client_shim_emits_deprecation_warning(self):
        import leasing.redis_client as shim

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            importlib.reload(shim)
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)


class TemplatetagLibraryTests(SimpleTestCase):
    def test_libraries_resolve_from_base_project(self):
        libraries = get_installed_libraries()
        assert libraries["url_tags"] == "base_project.templatetags.url_tags"
        assert libraries["qsargs_tags"] == "base_project.templatetags.qsargs_tags"
        assert libraries["lucide_tags"] == "base_project.templatetags.lucide_tags"


class TemplateResolutionTests(SimpleTestCase):
    def test_moved_templates_resolve_from_base_project(self):
        for name in MOVED_TEMPLATES:
            origin = get_template(name).origin.name
            assert "base_project" in origin, f"{name} resolved from {origin}"

    def test_base_templates_still_resolve_from_leasing_dirs(self):
        leasing_templates = str(Path(settings.BASE_DIR) / "templates")
        for name in ["base.html", "base_dashboard.html"]:
            origin = get_template(name).origin.name
            assert origin.startswith(leasing_templates), f"{name} resolved from {origin}"

    def test_skeleton_templates_exist_in_package(self):
        import base_project

        pkg_templates = Path(base_project.__file__).parent / "templates"
        assert (pkg_templates / "base.html").exists()
        assert (pkg_templates / "base_dashboard.html").exists()

    def test_pagination_template_renders(self):
        html = render_to_string("_pagination.html", {"is_paginated": False})
        assert "pagination" not in html  # not paginated -> no list rendered


class StaticFileTests(SimpleTestCase):
    def test_htmx_resolves_only_from_base_project(self):
        matches = finders.find("js/htmx.min.js", find_all=True)
        assert len(matches) == 1, f"expected a single htmx.min.js source, got {matches}"
        assert "base_project" in matches[0]

    def test_leasing_static_copy_is_gone(self):
        assert not (Path(settings.BASE_DIR) / "static" / "js" / "htmx.min.js").exists()


class MiddlewareWiringTests(SimpleTestCase):
    def test_db_middleware_setting_points_to_base_project(self):
        assert "base_project.middleware_db.DatabaseConnectionMiddleware" in settings.MIDDLEWARE
        assert not any("leasing.middleware_db" in entry for entry in settings.MIDDLEWARE)

    def test_asgi_uses_base_project_coop_middleware(self):
        from base_project.middleware_coop import COOPMiddleware
        from leasing import asgi

        assert isinstance(asgi.application.application_mapping["http"], COOPMiddleware)
