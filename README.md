# dj-base-project

Django app package `base_project` (app label und Importpfad bleiben
`base_project`, keine Models/Migrations). Host-Projekte pinnen dieses Repo als
Poetry-git-Dependency auf `main` — jeder Push auf main ist sofort releasebar.

Inhalt:

- **Base-Templates**: `base.html` / `base_dashboard.html` (generische
  Skeletons), `base_container.html`, `base_container_fluid.html`,
  `base_form.html`, `empty.html`, `_pagination.html`, `_empty.html`,
  `_message.html`, `_breadcrumb.html`.
- **Templatetags**: `url_tags` (aktive-URL-Helfer), `qsargs_tags`
  (Querystring-Manipulation), `lucide_tags` (`{% icon %}` / `{% lucide %}`
  fuer lokal servierte Lucide-SVGs).
- **Static**: `js/htmx.min.js` (lokal serviert, kein CDN).
- **Core-Utils**: `redis_client` (RedisClient mit pybreaker-Circuit-Breaker +
  Retry/Backoff, `get_redis_client_from_env()`), `redis_lock` (`RedisLock`,
  `AutoRenewingRedisLock`, `distributed_task`), `retry_utils`
  (`RetryStrategy`, `retry_with_backoff`), `middleware_coop`
  (COOP-Header fuer Channels/ASGI), `middleware_db`
  (DB-Reconnect-Middleware).

## Installation (Host-Projekt)

```toml
# pyproject.toml des Hosts (Single Lock Authority)
dj-base-project = {git = "ssh://git@github.com/sostrowsk/dj-base-project.git", branch = "main"}
```

```python
INSTALLED_APPS = [
    # ... Host-Apps zuerst ...
    "base_project.apps.BaseProjectConfig",  # am ENDE: Host-Templates/-Static
                                            # (DIRS-Loader) behalten Vorrang
]
```

## Settings-Katalog

| Setting | Pflicht | Default | Zweck |
| --- | --- | --- | --- |
| `BASE_DIR` | ja | — | Basis fuer den Lucide-Icon-Default-Pfad |
| `LUCIDE_ICONS_DIR` | nein | `BASE_DIR/node_modules/lucide-static/icons` | Verzeichnis der Lucide-SVGs fuer `{% icon %}`/`{% lucide %}` |

`redis_client.get_redis_client_from_env()` liest **Umgebungsvariablen** (keine
Django-Settings): `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`
(Fallback: `CELERY_BROKER_URL`, Default `redis://localhost:6379/0`) sowie
`REDIS_RETRY_ENABLED`, `REDIS_INITIAL_RETRY_DELAY`, `REDIS_MAX_RETRY_DELAY`,
`REDIS_MAX_RETRIES`, `REDIS_BACKOFF_FACTOR`, `REDIS_JITTER`.

## Host-Contract

- **Template-Override per DIRS-Loader**: Die Package-Templates sind generische
  Skeletons. Hosts ueberschreiben `base.html`/`base_dashboard.html` etc. durch
  gleichnamige Dateien in den Projekt-`TEMPLATES["DIRS"]` (App am Ende von
  `INSTALLED_APPS` ⇒ Projekt gewinnt).
- `empty.html` inkludiert `_favicon.html` — muss der Host bereitstellen (oder
  `empty.html` komplett overriden).
- `base_dashboard.html` laedt `js/htmx.min.js` via `{% static %}` — kommt aus
  diesem Package; `collectstatic` genuegt.
- Lucide-Icons: Host serviert `lucide-static` lokal (npm) oder setzt
  `LUCIDE_ICONS_DIR`.
- Middleware-Wiring (optional, vom Host explizit einzutragen):
  `base_project.middleware_db.EnsureDbConnectionMiddleware` in `MIDDLEWARE`,
  `base_project.middleware_coop.COOPMiddleware` im ASGI-Stack (Channels).

## Peer-Matrix

Keine Peer-Packages und keine Host-App-Imports — `base_project` ist die
unterste Schicht.

## Tests

Reine Unit-Tests (`base_project/tests/`), lauffaehig aus dem Host:

```bash
pytest --pyargs base_project.tests
```

`test_imports.py` enthaelt Shim-Identitaets-Tests fuer das leasing-Hostprojekt
(`leasing.redis_client` etc.) — in Fremd-Hosts schlagen genau diese Tests
fehl (dokumentierter leasing-Host-Contract). `test_redis_lock.py` und
`test_lucide_tags.py` sind host-neutral.

## Dev-Workflow

```bash
# Im Host lokal gegen den Working Tree entwickeln:
poetry run pip install -e ../dj-base-project   # poetry install setzt zurueck!

# Release: hier committen + auf main pushen, dann im Host:
poetry update dj-base-project
```

Uebersetzungen: `django-admin makemessages -l de` im `base_project/`-Ordner,
`.po` pflegen, `django-admin compilemessages`, `.mo` committen.
