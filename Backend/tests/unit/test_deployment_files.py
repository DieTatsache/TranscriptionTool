"""The deployment files agree with the settings they configure.

docker-compose*.yml and the two .env templates repeat setting names and defaults. A misspelled
SONORA_ variable is silently ignored, a new setting can be forgotten in the templates and a
default changed in one place drifts from the others; these tests catch all three.
"""

import re
from pathlib import Path

import pytest
import yaml

from sonora.config import Environment, Settings

REPO = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO / "docker-compose.yml"
COMPOSE_FILES = sorted(REPO.glob("docker-compose*.yml"))
ROOT_TEMPLATE = REPO / ".env.example"
BACKEND_TEMPLATE = REPO / "Backend" / ".env.example"
SETTING_VARIABLES = {f"SONORA_{name.upper()}" for name in Settings.model_fields}
# ${NAME}, ${NAME:-default} or ${NAME:?error message}
VARIABLE = re.compile(r"\$\{(\w+)(?::([-?])([^}]*))?\}")
# Where the Docker stack deliberately differs from the development defaults in config.py.
DOCKER_DEFAULTS = {
    "SONORA_LLM_CONTEXT_TOKENS": "32768",
    "SONORA_LLM_TIMEOUT_SECONDS": "900",
    "SONORA_WHISPER_MODEL": "large-v3-turbo",
}

pytestmark = pytest.mark.skipif(
    not COMPOSE_FILES, reason="the deployment files are not part of this checkout"
)


def entries(path: Path) -> list[tuple[str, str, bool]]:
    """(name, value, commented out) of every KEY=value line."""
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if match := re.fullmatch(r"(#?)\s*([A-Z][A-Z0-9_]*)=(.*)", line.strip()):
            found.append((match[2], match[3], match[1] == "#"))
    return found


def template(path: Path) -> dict[str, str]:
    return {name: value for name, value, _ in entries(path)}


def compose_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in COMPOSE_FILES)


def compose_defaults(name: str) -> set[str]:
    return {m[3] for m in VARIABLE.finditer(compose_text()) if m[1] == name and m[2] == "-"}


def stack_environment() -> dict[str, str]:
    """The SONORA_ variables docker-compose.yml sets for the API, worker and migrations."""
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    return {key: str(value) for key, value in compose["x-backend-env"].items()}


def mapped_default(value: str) -> str | None:
    """The default of a plain ${NAME:-default} mapping; None for values the stack fixes."""
    match = VARIABLE.fullmatch(value)
    return match[3] if match and match[2] == "-" else None


def field(variable: str) -> str:
    return variable.removeprefix("SONORA_").lower()


def test_compose_files_only_set_existing_settings() -> None:
    used = set(re.findall(r"\bSONORA_[A-Z0-9_]+", compose_text()))
    assert used - SETTING_VARIABLES == set()


def test_the_templates_only_name_existing_settings() -> None:
    named = set(template(BACKEND_TEMPLATE)) | {
        key for key in template(ROOT_TEMPLATE) if key.startswith("SONORA_")
    }
    assert named - SETTING_VARIABLES == set()


def test_the_backend_template_lists_every_setting_once() -> None:
    assert sorted(name for name, _, _ in entries(BACKEND_TEMPLATE)) == sorted(SETTING_VARIABLES)


def test_the_docker_template_lists_every_setting_the_stack_leaves_open() -> None:
    set_by_stack = set(stack_environment())
    listed = [name for name, _, _ in entries(ROOT_TEMPLATE) if name.startswith("SONORA_")]
    # A SONORA_ line for a setting docker-compose.yml sets itself would have no effect.
    assert set(listed) & set_by_stack == set()
    assert sorted(listed) == sorted(SETTING_VARIABLES - set_by_stack)


def test_the_docker_template_names_the_settings_the_stack_fixes() -> None:
    fixed = {key for key, value in stack_environment().items() if mapped_default(value) is None}
    text = ROOT_TEMPLATE.read_text(encoding="utf-8")
    assert set(re.findall(r"\bSONORA_[A-Z0-9_]+\b(?!=)", text)) == fixed


@pytest.mark.parametrize("path", [BACKEND_TEMPLATE, ROOT_TEMPLATE], ids=["backend", "docker"])
def test_commented_settings_show_their_defaults(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = Settings(_env_file=None)  # type: ignore[call-arg]
    for name, value, commented in entries(path):
        default = getattr(defaults, field(name), None)
        if not commented or not name.startswith("SONORA_") or default is None:
            continue  # active line, compose variable, or an example for an unset setting
        monkeypatch.setenv(name, value)
        assert getattr(Settings(_env_file=None), field(name)) == default, name  # type: ignore[call-arg]
        monkeypatch.delenv(name)


def test_the_backend_template_is_valid_as_is_and_with_every_line_uncommented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_is = Settings(_env_file=BACKEND_TEMPLATE)  # type: ignore[call-arg]
    assert as_is.environment is Environment.DEVELOPMENT
    for name, value, _ in entries(BACKEND_TEMPLATE):
        monkeypatch.setenv(name, value)
    assert Settings(_env_file=None).environment is Environment.DEVELOPMENT  # type: ignore[call-arg]


def test_every_compose_variable_is_documented_in_the_template() -> None:
    used = {m[1] for m in VARIABLE.finditer(compose_text())}
    assert used - set(template(ROOT_TEMPLATE)) == set()


def test_the_template_has_no_variables_compose_does_not_use() -> None:
    used = {m[1] for m in VARIABLE.finditer(compose_text())}
    short_names = {name for name in template(ROOT_TEMPLATE) if not name.startswith("SONORA_")}
    assert short_names - used == set()


def test_the_template_repeats_the_compose_defaults() -> None:
    # Copying .env.example must behave like an empty .env.
    documented = template(ROOT_TEMPLATE)
    for match in VARIABLE.finditer(compose_text()):
        name, kind, default = match[1], match[2], match[3]
        if kind == "-" and documented.get(name):
            assert documented[name] == default, name


def test_docker_keeps_the_code_defaults_except_where_intended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = Settings(_env_file=None)  # type: ignore[call-arg]
    for key, value in stack_environment().items():
        default = mapped_default(value)
        if default is None:
            continue  # fixed by the stack (production mode, service addresses, paths)
        monkeypatch.setenv(key, default)
        in_docker = getattr(Settings(_env_file=None), field(key))  # type: ignore[call-arg]
        monkeypatch.delenv(key)
        if key in DOCKER_DEFAULTS:
            assert default == DOCKER_DEFAULTS[key], key
            assert in_docker != getattr(defaults, field(key)), f"{key} no longer differs"
        else:
            assert in_docker == getattr(defaults, field(key)), key


def test_one_llm_model_everywhere() -> None:
    model = Settings.model_fields["llm_model"].default
    assert template(ROOT_TEMPLATE)["LLM_MODEL"] == model
    assert template(BACKEND_TEMPLATE)["SONORA_LLM_MODEL"] == model
    assert compose_defaults("LLM_MODEL") == {model}


def test_the_compose_stack_passes_the_production_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    documented = template(ROOT_TEMPLATE)
    secrets = {"POSTGRES_PASSWORD": "only-for-this-test"}  # left empty in the template

    def interpolate(match: re.Match[str]) -> str:
        name, kind, default = match[1], match[2], match[3]
        return documented.get(name) or secrets.get(name) or (default if kind == "-" else "")

    # Every SONORA_ line of the template uncommented, plus what the stack sets itself.
    for name, value in documented.items():
        if name.startswith("SONORA_"):
            monkeypatch.setenv(name, value)
    for key, value in stack_environment().items():
        monkeypatch.setenv(key, VARIABLE.sub(interpolate, value))

    loaded = Settings(_env_file=None)  # type: ignore[call-arg]
    assert loaded.environment is Environment.PRODUCTION
    assert loaded.cookie_secure
    assert loaded.llm_model == documented["LLM_MODEL"]
    assert loaded.allowed_hosts == [documented["PUBLIC_HOST"], "localhost"]
