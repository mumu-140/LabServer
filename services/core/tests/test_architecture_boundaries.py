import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTES_DIR = REPO_ROOT / "services/core/src/labserver_core/api/routes"
CONTRACTS_DIR = REPO_ROOT / "packages/contracts/src/labserver_contracts"


def imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def forbidden_imports(source: str, forbidden_prefixes: tuple[str, ...]) -> set[str]:
    return {
        module
        for module in imported_modules(source)
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    }


def test_import_checker_detects_forbidden_dependencies() -> None:
    source = """
from sqlalchemy import select
from labserver_core.persistence.models import UserModel
from labserver_core.application.user_service import UserService
"""

    assert forbidden_imports(source, ("sqlalchemy", "labserver_core.persistence")) == {
        "sqlalchemy",
        "labserver_core.persistence.models",
    }


def test_api_routes_do_not_import_persistence_or_sqlalchemy() -> None:
    violations: dict[str, set[str]] = {}
    for path in sorted(ROUTES_DIR.glob("*.py")):
        forbidden = forbidden_imports(
            path.read_text(encoding="utf-8"),
            ("sqlalchemy", "labserver_core.persistence"),
        )
        if forbidden:
            violations[str(path.relative_to(REPO_ROOT))] = forbidden

    assert violations == {}


def test_contracts_do_not_depend_on_core() -> None:
    violations: dict[str, set[str]] = {}
    for path in sorted(CONTRACTS_DIR.glob("*.py")):
        forbidden = forbidden_imports(path.read_text(encoding="utf-8"), ("labserver_core",))
        if forbidden:
            violations[str(path.relative_to(REPO_ROOT))] = forbidden

    assert violations == {}

GUARD_ROOTS = (
    REPO_ROOT / "packages/contracts/src",
    REPO_ROOT / "services/core/src",
    REPO_ROOT / "apps/web/src",
    REPO_ROOT / "docs/api",
)
GUARD_SUFFIXES = {".py", ".html", ".md", ".css"}
# Active product sources and current API docs must not expose the retired
# request/approval model. Historical specs/plans, migration SQL, and this
# guard's own test fixtures are out of scope by design.
APPROVAL_TERMS = re.compile(
    r"\bTaskRequest\w*"
    r"|\bReservation\w*"
    r"|\bapprov\w*"
    r"|\breject\w*"
    r"|/api/v1/requests"
    r"|/api/v1/reservations"
)


def test_active_sources_do_not_use_approval_terminology() -> None:
    violations: list[tuple[str, str]] = []
    for root in GUARD_ROOTS:
        for path in sorted(root.rglob("*")):
            if path.suffix not in GUARD_SUFFIXES or not path.is_file():
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            if "/vendor/" in f"/{relative}":
                continue
            for match in APPROVAL_TERMS.finditer(path.read_text(encoding="utf-8")):
                violations.append((relative, match.group(0)))

    assert violations == []
