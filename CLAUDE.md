# dj-base-project

Django app package `base_project` (app label und Importpfad bleiben
`base_project`; keine Models/Migrations). Host-Projekte pinnen dieses Repo als Poetry-git-Dependency auf
`main` — jeder Push auf main ist sofort releasebar.

## TDD-Regeln (Pflicht)

- **Test zuerst, RED bestaetigen, dann implementieren, GREEN bestaetigen.**
- Bugfix = Regressionstest, der den Bug reproduziert und VOR dem Fix failt.
- Reine Moves: Import-Smoke-Tests (`tests/test_imports.py`).
- Tests laufen aus dem Host-Projekt: `pytest --pyargs base_project.tests`
  (das Package hat keine eigene Settings-/pytest-Infrastruktur).

## Architektur-Regeln

- Keine Imports aus Host-Apps (users, project, leasing, ...). FK-Targets nur
  via `settings.AUTH_USER_MODEL` bzw. getattr-Settings mit stabilen Defaults.
- **Migrations-Byte-Stabilitaet:** Aenderungen duerfen keine neuen Migrationen
  im Host erzeugen (`makemigrations --check --dry-run` muss clean bleiben).
- Templates/Static/Locale liegen im Package und werden ins Wheel gepackt
  (include-Pattern in pyproject.toml beachten).
- Uebersetzungen: `django-admin makemessages -l de` im `base_project/`-Ordner,
  `.po` pflegen, `.mo` via compilemessages erzeugen und **committen**.
