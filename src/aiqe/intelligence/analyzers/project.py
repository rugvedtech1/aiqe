"""
AIQE Project Analyzer.

Deterministic analysis of a project's language, framework,
dependencies, and structure. Zero AI calls.

This is the foundation of the Project Analysis Agent (Tier 1).
The agent uses this analyzer to collect raw facts, then uses
the AI Gateway to generate higher-level insights.

Detection priority:
    1. Manifest files (pyproject.toml, package.json, etc.)
       — most reliable, machine-generated
    2. Framework-specific files (manage.py, next.config.js, etc.)
       — definitive indicator
    3. Import patterns in source files
       — fallback when manifests are absent
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

try:
    import tomllib
except ImportError:
    import tomllib  # type: ignore


@dataclass
class ProjectProfile:
    """
    The raw profile of a scanned project.

    Everything here is determined by deterministic analysis.
    No AI is involved in producing these values.

    Attributes:
        language: Primary programming language.
        framework: Primary web/application framework.
        test_framework: Testing framework in use.
        package_manager: Package manager (pip, npm, cargo, etc.)
        dependencies: List of detected dependencies.
        dev_dependencies: List of development dependencies.
        entry_points: Main entry point files.
        source_files: All detected source files.
        test_files: All detected test files.
        config_files: Configuration files found.
        has_docker: Whether Docker configuration exists.
        has_ci: Whether CI/CD configuration exists.
        has_database: Whether database usage is detected.
        has_api: Whether API routes are detected.
        has_auth: Whether authentication patterns are detected.
        database_type: Detected database type (if any).
        auth_method: Detected auth method (if any).
        lines_of_code: Approximate total lines of code.
        file_count: Total source file count.
        language_stats: Language distribution.
    """
    language: str = "unknown"
    framework: str = "unknown"
    test_framework: str = "unknown"
    package_manager: str = "unknown"
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    has_docker: bool = False
    has_ci: bool = False
    has_database: bool = False
    has_api: bool = False
    has_auth: bool = False
    database_type: str = ""
    auth_method: str = ""
    lines_of_code: int = 0
    file_count: int = 0
    language_stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "framework": self.framework,
            "test_framework": self.test_framework,
            "package_manager": self.package_manager,
            "dependencies": self.dependencies,
            "dev_dependencies": self.dev_dependencies,
            "entry_points": self.entry_points,
            "source_files": self.source_files[:50],
            "test_files": self.test_files[:50],
            "config_files": self.config_files,
            "has_docker": self.has_docker,
            "has_ci": self.has_ci,
            "has_database": self.has_database,
            "has_api": self.has_api,
            "has_auth": self.has_auth,
            "database_type": self.database_type,
            "auth_method": self.auth_method,
            "lines_of_code": self.lines_of_code,
            "file_count": self.file_count,
            "language_stats": self.language_stats,
        }


_AUTH_MARKERS = re.compile(
    r'(?:jwt|oauth|bearer|session|cookie|'
    r'login_required|authenticate|verify_token)',
    re.IGNORECASE,
)
_DB_MARKERS = re.compile(
    r'(?:sqlalchemy|django\.db|mongoose|prisma|'
    r'knex|sequelize|psycopg|pymongo|redis)',
    re.IGNORECASE,
)
_API_MARKERS = re.compile(
    r'(?:@app\.get|@app\.post|@router\.|'
    r'app\.use\(|router\.get|path\()',
    re.IGNORECASE,
)


class ProjectAnalyzer:
    """
    Analyses a project directory and produces a ProjectProfile.

    Pure deterministic analysis — no AI, no subprocess calls,
    no network requests.

    Args:
        project_path: Root directory of the project.
    """

    def __init__(self, project_path: Path) -> None:
        self._project_path = project_path

    def analyze(self) -> ProjectProfile:
        """
        Analyse the project and return a ProjectProfile.

        Returns:
            ProjectProfile with all detected project attributes.
        """
        logger.info(
            "project_analysis_started",
            project_path=str(self._project_path),
        )

        profile = ProjectProfile()

        # Step 1: Check for manifest files (most reliable)
        self._detect_from_python_manifests(profile)
        self._detect_from_js_manifests(profile)
        self._detect_from_ruby_manifests(profile)
        self._detect_from_rust_manifests(profile)

        # Step 2: Framework-specific file detection
        if profile.language == "unknown":
            self._detect_language_from_files(profile)

        self._detect_framework(profile)
        self._detect_test_framework(profile)

        # Step 3: Infrastructure detection
        self._detect_docker(profile)
        self._detect_ci(profile)

        # Step 4: Collect source and test files
        self._collect_files(profile)

        # Step 5: Pattern-based detection on source files
        self._detect_from_source_patterns(profile)

        # Step 6: Count lines of code
        self._count_loc(profile)

        logger.info(
            "project_analysis_complete",
            language=profile.language,
            framework=profile.framework,
            test_framework=profile.test_framework,
            dependencies=len(profile.dependencies),
            source_files=len(profile.source_files),
            test_files=len(profile.test_files),
            has_docker=profile.has_docker,
            has_ci=profile.has_ci,
        )

        return profile

    def _detect_from_python_manifests(
        self, profile: ProjectProfile
    ) -> None:
        """Detect Python project config from pyproject.toml, setup.py, etc."""
        # pyproject.toml
        pyproject = self._project_path / "pyproject.toml"
        if pyproject.exists():
            try:
                data = tomllib.loads(
                    pyproject.read_text(encoding="utf-8")
                )
                profile.language = "python"
                profile.package_manager = "pip"
                profile.config_files.append("pyproject.toml")

                deps = (
                    data.get("project", {}).get("dependencies", []) or
                    data.get("tool", {}).get("poetry", {}).get(
                        "dependencies", {}
                    )
                )
                if isinstance(deps, list):
                    profile.dependencies = [
                        d.split("[")[0].split(">=")[0].strip()
                        for d in deps
                    ]
                elif isinstance(deps, dict):
                    profile.dependencies = [
                        k for k in deps if k != "python"
                    ]

                dev_deps = (
                    data.get("tool", {}).get("poetry", {}).get(
                        "dev-dependencies", {}
                    ) or
                    data.get("project", {}).get(
                        "optional-dependencies", {}
                    ).get("dev", [])
                )
                if isinstance(dev_deps, dict):
                    profile.dev_dependencies = list(dev_deps.keys())
                elif isinstance(dev_deps, list):
                    profile.dev_dependencies = dev_deps

                return
            except Exception:
                pass

        # requirements.txt
        req_file = self._project_path / "requirements.txt"
        if req_file.exists():
            profile.language = "python"
            profile.package_manager = "pip"
            profile.config_files.append("requirements.txt")
            try:
                lines = req_file.read_text(encoding="utf-8").splitlines()
                profile.dependencies = [
                    line.split("==")[0].split(">=")[0].strip()
                    for line in lines
                    if line.strip() and not line.startswith("#")
                ]
            except Exception:
                pass

        # setup.py
        setup_py = self._project_path / "setup.py"
        if setup_py.exists() and profile.language == "unknown":
            profile.language = "python"
            profile.package_manager = "pip"
            profile.config_files.append("setup.py")

    def _detect_from_js_manifests(
        self, profile: ProjectProfile
    ) -> None:
        """Detect JS/TS project config from package.json."""
        package_json = self._project_path / "package.json"
        if not package_json.exists():
            return

        try:
            data = json.loads(
                package_json.read_text(encoding="utf-8")
            )
            if profile.language == "unknown":
                # Check for TypeScript
                if (self._project_path / "tsconfig.json").exists():
                    profile.language = "typescript"
                else:
                    profile.language = "javascript"

            # Detect package manager
            if (self._project_path / "yarn.lock").exists():
                profile.package_manager = "yarn"
            elif (self._project_path / "pnpm-lock.yaml").exists():
                profile.package_manager = "pnpm"
            else:
                profile.package_manager = "npm"

            profile.config_files.append("package.json")

            deps = data.get("dependencies", {})
            dev_deps = data.get("devDependencies", {})
            profile.dependencies = list(deps.keys())
            profile.dev_dependencies = list(dev_deps.keys())

            # Main entry point
            if data.get("main"):
                profile.entry_points.append(data["main"])

        except Exception:
            pass

    def _detect_from_ruby_manifests(
        self, profile: ProjectProfile
    ) -> None:
        """Detect Ruby project config."""
        gemfile = self._project_path / "Gemfile"
        if gemfile.exists() and profile.language == "unknown":
            profile.language = "ruby"
            profile.package_manager = "bundler"
            profile.config_files.append("Gemfile")

    def _detect_from_rust_manifests(
        self, profile: ProjectProfile
    ) -> None:
        """Detect Rust project config."""
        cargo = self._project_path / "Cargo.toml"
        if cargo.exists() and profile.language == "unknown":
            profile.language = "rust"
            profile.package_manager = "cargo"
            profile.config_files.append("Cargo.toml")

    def _detect_language_from_files(
        self, profile: ProjectProfile
    ) -> None:
        """Count source files per language to determine primary language."""
        ext_counts: dict[str, int] = {}
        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".rb": "ruby",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".kt": "kotlin",
            ".cs": "csharp",
            ".php": "php",
        }

        for ext, lang in ext_to_lang.items():
            count = len(list(self._project_path.rglob(f"*{ext}")))
            if count > 0:
                ext_counts[lang] = ext_counts.get(lang, 0) + count

        if ext_counts:
            profile.language = max(ext_counts, key=ext_counts.get)  # type: ignore
            profile.language_stats = ext_counts

    def _detect_framework(self, profile: ProjectProfile) -> None:
        """Detect the primary framework from dependencies and files."""
        deps_lower = {d.lower() for d in profile.dependencies}

        # Python frameworks
        python_frameworks = {
            "fastapi": "fastapi",
            "django": "django",
            "flask": "flask",
            "starlette": "starlette",
            "tornado": "tornado",
            "aiohttp": "aiohttp",
            "sanic": "sanic",
        }

        # JS frameworks
        js_frameworks = {
            "react": "react",
            "next": "nextjs",
            "vue": "vue",
            "nuxt": "nuxt",
            "angular": "angular",
            "svelte": "svelte",
            "express": "express",
            "nestjs": "nestjs",
            "fastify": "fastify",
        }

        # File-based detection
        if (self._project_path / "manage.py").exists():
            profile.framework = "django"
            return

        if (self._project_path / "next.config.js").exists() or \
                (self._project_path / "next.config.ts").exists():
            profile.framework = "nextjs"
            return

        # Dependency-based detection
        for dep, framework in {**python_frameworks, **js_frameworks}.items():
            if dep in deps_lower:
                profile.framework = framework
                break

    def _detect_test_framework(
        self, profile: ProjectProfile
    ) -> None:
        """Detect testing framework from dependencies and config files."""
        deps_lower = {d.lower() for d in profile.dependencies + profile.dev_dependencies}

        test_frameworks = {
            "pytest": "pytest",
            "unittest": "unittest",
            "jest": "jest",
            "mocha": "mocha",
            "jasmine": "jasmine",
            "vitest": "vitest",
            "cypress": "cypress",
            "playwright": "playwright",
            "rspec": "rspec",
        }

        for dep, framework in test_frameworks.items():
            if dep in deps_lower:
                profile.test_framework = framework
                break

        # Check for pytest.ini / pytest config
        if profile.test_framework == "unknown":
            if any([
                (self._project_path / "pytest.ini").exists(),
                (self._project_path / "conftest.py").exists(),
                any(self._project_path.glob("**/conftest.py")),
            ]):
                profile.test_framework = "pytest"

    def _detect_docker(self, profile: ProjectProfile) -> None:
        """Detect Docker configuration."""
        docker_files = [
            "Dockerfile", "docker-compose.yml",
            "docker-compose.yaml", ".dockerignore",
        ]
        for docker_file in docker_files:
            if (self._project_path / docker_file).exists():
                profile.has_docker = True
                profile.config_files.append(docker_file)

    def _detect_ci(self, profile: ProjectProfile) -> None:
        """Detect CI/CD configuration."""
        ci_indicators = [
            ".github/workflows",
            ".gitlab-ci.yml",
            ".circleci/config.yml",
            "Jenkinsfile",
            ".travis.yml",
            "azure-pipelines.yml",
        ]
        for indicator in ci_indicators:
            ci_path = self._project_path / indicator
            if ci_path.exists():
                profile.has_ci = True
                profile.config_files.append(indicator)

    def _collect_files(self, profile: ProjectProfile) -> None:
        """Collect source and test file lists."""
        lang_extensions = {
            "python": [".py"],
            "javascript": [".js", ".jsx"],
            "typescript": [".ts", ".tsx"],
            "ruby": [".rb"],
            "go": [".go"],
            "rust": [".rs"],
            "java": [".java"],
        }

        skip_dirs = {
            ".git", ".venv", "venv", "node_modules",
            "__pycache__", "dist", "build", "htmlcov",
        }

        exts = lang_extensions.get(profile.language, [".py"])
        test_patterns = {
            "test_", "_test", "_spec", "spec_",
            ".test.", ".spec.",
        }

        all_source = []
        all_tests = []

        for ext in exts:
            for file_path in self._project_path.rglob(f"*{ext}"):
                if any(p in skip_dirs for p in file_path.parts):
                    continue
                rel = str(file_path.relative_to(self._project_path))
                name = file_path.name
                if any(p in name for p in test_patterns):
                    all_tests.append(rel)
                else:
                    all_source.append(rel)

        profile.source_files = all_source
        profile.test_files = all_tests
        profile.file_count = len(all_source) + len(all_tests)

    def _detect_from_source_patterns(
        self, profile: ProjectProfile
    ) -> None:
        """Detect auth, database, and API usage from source patterns."""
        files_to_scan = [
            self._project_path / f
            for f in profile.source_files[:30]
        ]

        for file_path in files_to_scan:
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )

                if not profile.has_auth and _AUTH_MARKERS.search(content):
                    profile.has_auth = True

                if not profile.has_database and _DB_MARKERS.search(content):
                    profile.has_database = True
                    # Detect specific database
                    if "postgres" in content.lower() or "psycopg" in content.lower():
                        profile.database_type = "postgresql"
                    elif "mysql" in content.lower():
                        profile.database_type = "mysql"
                    elif "sqlite" in content.lower():
                        profile.database_type = "sqlite"
                    elif "mongodb" in content.lower() or "pymongo" in content.lower():
                        profile.database_type = "mongodb"

                if not profile.has_api and _API_MARKERS.search(content):
                    profile.has_api = True

            except (OSError, PermissionError):
                continue

    def _count_loc(self, profile: ProjectProfile) -> None:
        """Count approximate lines of code."""
        total = 0
        for rel_path in profile.source_files[:200]:
            file_path = self._project_path / rel_path
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                total += len([
                    line for line in content.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ])
            except (OSError, PermissionError):
                continue
        profile.lines_of_code = total
