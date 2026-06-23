#!/usr/bin/env python3
"""
NarrativeOS Debug Script
Kiểm tra toàn bộ hệ thống: config, database, Redis, LLM, ChromaDB, API endpoints.

Cách dùng:
    python debug.py               # Chạy tất cả kiểm tra
    python debug.py --section db  # Chỉ kiểm tra database
    python debug.py --section llm # Chỉ kiểm tra LLM
    python debug.py --api-url http://localhost:8000  # Custom API URL
    python debug.py --verbose     # Hiển thị chi tiết lỗi đầy đủ
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import socket
import sys
import time
import traceback
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen
from backend.llm.providers.base import LLMMessage
from backend.rag import NarrativeMemoryService
from chromadb.config import Settings
# ─── Màu sắc terminal ──────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"

OK = f"{GREEN}✓{RESET}"
FAIL = f"{RED}✗{RESET}"
WARN = f"{YELLOW}⚠{RESET}"
INFO = f"{CYAN}ℹ{RESET}"


def ok(msg: str) -> str:
    return f"  {OK}  {msg}"


def fail(msg: str, detail: str = "") -> str:
    line = f"  {FAIL}  {msg}"
    if detail:
        line += f"\n{DIM}       {detail}{RESET}"
    return line


def warn(msg: str) -> str:
    return f"  {WARN}  {msg}"


def info(msg: str) -> str:
    return f"  {INFO}  {msg}"


def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN} {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")


def header(title: str) -> None:
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    print(f"{BOLD}  NarrativeOS Debug  —  {title}{RESET}")
    print(f"{BOLD}{'═' * 60}{RESET}")


# ─── Helpers ───────────────────────────────────────────────────────────────────

def http_get(url: str, timeout: float = 3.0) -> tuple[int, Any]:
    """Gửi GET request đơn giản, trả về (status_code, parsed_body)."""
    try:
        with urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except URLError as exc:
        raise ConnectionError(str(exc)) from exc


def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ─── Section 1: Môi trường ─────────────────────────────────────────────────────

def check_environment(verbose: bool = False) -> int:
    section("1. Môi trường & Cấu hình")
    errors = 0

    # Thư mục gốc
    root = Path(__file__).parent
    print(ok(f"Thư mục gốc: {root}"))

    # Python version
    py = sys.version.split()[0]
    major, minor = sys.version_info[:2]
    if major == 3 and minor >= 11:
        print(ok(f"Python {py}"))
    else:
        print(warn(f"Python {py} — khuyến nghị >= 3.11"))

    # .env file
    env_file = root / ".env"
    if env_file.exists():
        print(ok(".env tồn tại"))
    else:
        print(warn(".env không tồn tại — dùng giá trị mặc định từ .env.example"))

    # Load settings
    sys.path.insert(0, str(root))
    try:
        from backend.core.config import get_settings
        settings = get_settings()
        print(ok("backend.core.config tải thành công"))
    except Exception as exc:
        print(fail("Không thể tải Settings", str(exc) if verbose else ""))
        return errors + 1

    # In các biến quan trọng
    pairs = [
        ("APP_NAME", settings.app_name),
        ("ENVIRONMENT", settings.environment),
        ("DEBUG", str(settings.debug)),
        ("DATABASE_URL", _mask(settings.database_url)),
        ("REDIS_URL", _mask(settings.redis_url)),
        ("LLM_PROVIDER", settings.llm_provider),
        ("LLM_MODEL", settings.llm_model),
        ("LLM_BASE_URL", settings.llm_base_url or "(chưa đặt)"),
        ("OPENAI_API_KEY", "***" if settings.openai_api_key else "(chưa đặt)"),
        ("ANTHROPIC_API_KEY", "***" if settings.anthropic_api_key else "(chưa đặt)"),
    ]
    for key, val in pairs:
        print(info(f"{key} = {val}"))

    # Cảnh báo secret mặc định
    if settings.secret_key == "change-me-in-production":
        print(warn("SECRET_KEY vẫn là giá trị mặc định — KHÔNG dùng cho production!"))

    return errors


def _mask(url: str) -> str:
    """Che mật khẩu trong URL."""
    import re
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1****\2", url)


# ─── Section 2: Database ───────────────────────────────────────────────────────

def check_database(verbose: bool = False) -> int:
    section("2. Database (SQLAlchemy)")
    errors = 0

    try:
        from backend.core.config import get_settings
        from backend.database.session import engine, Base
        settings = get_settings()
    except Exception as exc:
        print(fail("Import database modules thất bại", str(exc) if verbose else ""))
        return 1

    db_url = settings.database_url

    # Kiểm tra driver
    if "postgresql" in db_url or "postgres" in db_url:
        driver = "PostgreSQL"
        host_part = db_url.split("@")[-1].split("/")[0] if "@" in db_url else "localhost:5432"
        host, _, port_str = host_part.partition(":")
        port = int(port_str) if port_str.isdigit() else 5432
        if check_port(host, port):
            print(ok(f"{driver} port {host}:{port} mở"))
        else:
            print(fail(f"{driver} port {host}:{port} không thể kết nối"))
            errors += 1
    elif "sqlite" in db_url:
        driver = "SQLite"
        print(info(f"Dùng SQLite: {db_url}"))
    else:
        driver = db_url.split(":")[0]
        print(info(f"Driver: {driver}"))

    # Thử kết nối thực tế
    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        print(ok(f"{driver} kết nối thành công"))
    except Exception as exc:
        detail = traceback.format_exc() if verbose else str(exc)
        print(fail(f"{driver} kết nối thất bại", detail))
        errors += 1
        return errors

    # Kiểm tra bảng
    try:
        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(engine)
        tables = inspector.get_table_names()
        if tables:
            print(ok(f"Tìm thấy {len(tables)} bảng: {', '.join(sorted(tables)[:8])}{'...' if len(tables) > 8 else ''}"))
        else:
            print(warn("Database không có bảng — cần chạy migration (alembic upgrade head)"))
    except Exception as exc:
        print(warn(f"Không thể liệt kê bảng: {exc}"))

    # Thử import models
    try:
        from backend.database.models import (  # noqa: F401
            project, user, character, scene, timeline_event,
        )
        print(ok("Models SQLAlchemy import thành công"))
    except Exception as exc:
        detail = traceback.format_exc() if verbose else str(exc)
        print(fail("Models import thất bại", detail))
        errors += 1

    return errors


# ─── Section 3: Redis ──────────────────────────────────────────────────────────

def check_redis(verbose: bool = False) -> int:
    section("3. Redis (Cache & Rate Limiter)")
    errors = 0

    try:
        from backend.cache.redis_client import RedisClient

        client = RedisClient().client

        # test cache thực tế
        test_key = "debug_test"
        test_value = "ok"

        client.set(test_key, test_value)
        value = client.get(test_key)

        if value == test_value:
            backend_name = type(client).__name__

            print(ok(f"Cache hoạt động ({backend_name})"))

            if backend_name == "InMemoryRedis":
                print(warn("Redis server không chạy — đang dùng InMemoryRedis fallback"))
            else:
                print(ok("Redis server hoạt động bình thường"))

        else:
            print(fail("Cache trả dữ liệu không chính xác"))
            errors += 1

    except Exception as exc:
        detail = traceback.format_exc() if verbose else str(exc)
        print(fail("Cache layer lỗi", detail))
        errors += 1

    return errors


# ─── Section 4: LLM Provider ──────────────────────────────────────────────────

def check_llm(verbose: bool = False) -> int:
    section("4. LLM Provider")
    errors = 0

    try:
        from backend.core.config import get_settings
        settings = get_settings()
    except Exception as exc:
        print(fail("Không tải được settings", str(exc) if verbose else ""))
        return 1

    provider = (settings.llm_provider or "qwen").lower()
    model = settings.llm_model
    base_url = settings.llm_base_url
    print(info(f"Provider: {provider}"))
    print(info(f"Model: {model}"))
    print(info(f"Base URL: {base_url or '(chưa đặt)'}"))

    if provider in ("qwen", "openai"):
        if not base_url:
            print(warn("LLM_BASE_URL chưa đặt — cần Ollama hoặc OpenAI-compatible endpoint"))
            errors += 1
        else:
            # Kiểm tra port
            try:
                from urllib.parse import urlparse
                parsed = urlparse(base_url)
                host = parsed.hostname or "127.0.0.1"
                port = parsed.port or 11434
                if check_port(host, port):
                    print(ok(f"LLM endpoint port {host}:{port} mở"))
                else:
                    print(fail(f"LLM endpoint {host}:{port} không thể kết nối"))
                    errors += 1
                    return errors
            except Exception:
                pass

            # Probe /models
            models_url = base_url.rstrip("/").rstrip("/v1") + "/api/tags"
            ollama_url = base_url.rstrip("/").replace("/v1", "") + "/api/tags"
            openai_models_url = base_url.rstrip("/") + "/models"

            found_models: list[str] = []
            for probe_url in [openai_models_url, ollama_url, models_url]:
                try:
                    status, data = http_get(probe_url, timeout=3.0)
                    if status == 200:
                        # OpenAI format
                        if isinstance(data, dict) and "data" in data:
                            found_models = [m.get("id", "") for m in data["data"] if isinstance(m, dict)]
                        # Ollama format
                        elif isinstance(data, dict) and "models" in data:
                            found_models = [m.get("name", "") for m in data["models"] if isinstance(m, dict)]
                        if found_models:
                            print(ok(f"Endpoint trả về {len(found_models)} models"))
                            print(info(f"Models: {', '.join(found_models[:5])}{'...' if len(found_models) > 5 else ''}"))
                            break
                except Exception:
                    continue

            if model and found_models:
                model_names = [m.split(":")[0] if ":" in m else m for m in found_models]
                if model in found_models or model.split(":")[0] in model_names:
                    print(ok(f"Model '{model}' có sẵn"))
                else:
                    print(warn(f"Model '{model}' không tìm thấy trong danh sách endpoint"))

    elif provider == "anthropic":
        if settings.anthropic_api_key:
            print(ok("ANTHROPIC_API_KEY đã đặt"))
        else:
            print(fail("ANTHROPIC_API_KEY chưa đặt"))
            errors += 1

    # Thử khởi tạo provider
    try:
        from backend.llm.providers import create_llm_provider
        llm = create_llm_provider(provider)
        print(ok(f"LLM provider '{provider}' khởi tạo thành công: {type(llm).__name__}"))
    except Exception as exc:
        detail = traceback.format_exc() if verbose else str(exc)
        print(fail(f"Khởi tạo LLM provider thất bại", detail))
        errors += 1

    # Thử gọi LLM nhanh
    try:
        from backend.llm.providers import create_llm_provider
        llm = create_llm_provider(provider)
        t0 = time.time()
        response = llm.complete([
            LLMMessage(
                role="user",
                content="Trả lời đúng 1 từ: xin chào"
    )
])
        elapsed = time.time() - t0
        content = getattr(response, "content", str(response))[:80]
        print(ok(f"LLM invoke thành công ({elapsed:.2f}s): '{content}'"))
    except Exception as exc:
        detail = traceback.format_exc() if verbose else str(exc)
        print(warn(f"LLM invoke thất bại (có thể bình thường nếu model chưa load): {str(exc)[:100]}"))

    return errors


# ─── Section 5: API Server ─────────────────────────────────────────────────────

def check_api(api_url: str = "http://localhost:8000", verbose: bool = False) -> int:
    section(f"5. API Server ({api_url})")
    errors = 0

    endpoints = [
        ("GET", "/", "root"),
        ("GET", "/health", "health check"),
        ("GET", "/meta", "metadata"),
        ("GET", "/projects", "projects list (cần auth)"),
    ]

    for method, path, label in endpoints:
        url = api_url.rstrip("/") + path
        try:
            status, data = http_get(url, timeout=3.0)
            if status == 200:
                print(ok(f"{method} {path} → {status} ({label})"))
                if verbose and isinstance(data, dict):
                    print(DIM + f"       {json.dumps(data, ensure_ascii=False)[:120]}" + RESET)
            elif status in (401, 403):
                print(warn(f"{method} {path} → {status} (cần xác thực — bình thường)"))
            else:
                print(warn(f"{method} {path} → {status}"))
        except ConnectionError as exc:
            print(fail(f"{method} {path} — không thể kết nối", str(exc) if verbose else "Server chưa chạy?"))
            errors += 1
            break  # Nếu root không kết nối được thì bỏ qua phần còn lại
        except Exception as exc:
            detail = traceback.format_exc() if verbose else str(exc)
            print(fail(f"{method} {path} thất bại", detail))
            errors += 1

    return errors


# ─── Section 6: Imports ────────────────────────────────────────────────────────

def check_imports(verbose: bool = False) -> int:
    section("6. Import Modules Quan Trọng")
    errors = 0

    modules = [
        ("fastapi", "FastAPI"),
        ("sqlalchemy", "SQLAlchemy"),
        ("pydantic", "Pydantic"),
        ("langchain_core", "LangChain Core"),
        ("chromadb", "ChromaDB"),
        ("sentence_transformers", "Sentence Transformers"),
        ("redis", "redis-py"),
        ("alembic", "Alembic"),
        ("uvicorn", "Uvicorn"),
        ("jose", "python-jose (JWT)"),
        ("passlib", "Passlib"),
    ]

    for module_name, label in modules:
        try:
            mod = importlib.import_module(module_name)
            version = getattr(mod, "__version__", "?")
            print(ok(f"{label} ({version})"))
        except ImportError as exc:
            print(fail(f"{label} chưa cài", str(exc) if verbose else ""))
            errors += 1

    # Kiểm tra backend modules
    backend_modules = [
        ("backend.core.config", "core.config"),
        ("backend.database.session", "database.session"),
        ("backend.narrative.state_engine", "narrative.state_engine"),
        ("backend.narrative.query_system", "narrative.query_system"),
        ("backend.consistency.agents.critic_agent", "consistency.critic_agent"),
        ("backend.rag.context_builder.narrative_memory", "rag.narrative_memory"),
    ]

    print()
    for module_name, label in backend_modules:
        try:
            importlib.import_module(module_name)
            print(ok(f"backend.{label}"))
        except Exception as exc:
            detail = traceback.format_exc() if verbose else str(exc)
            print(fail(f"backend.{label}", detail))
            errors += 1

    return errors


# ─── Section 7: ChromaDB / Vector Store ───────────────────────────────────────

def check_vectorstore(verbose: bool = False) -> int:
    section("7. Vector Store (ChromaDB)")
    errors = 0

    try:
        import chromadb
        print(ok(f"chromadb {chromadb.__version__} import thành công"))
    except ImportError:
        print(fail("chromadb chưa cài"))
        return 1

    # Test ChromaDB
    try:
        from chromadb.config import Settings

        client = chromadb.EphemeralClient(
            settings=Settings(
                anonymized_telemetry=False
            )
        )

        col = client.get_or_create_collection("debug_test")

        col.add(
            documents=["test document"],
            ids=["test-1"]
        )

        results = col.query(
            query_texts=["test"],
            n_results=1
        )

        client.delete_collection("debug_test")

        print(ok("ChromaDB in-memory client hoạt động"))

    except Exception as exc:
        detail = traceback.format_exc() if verbose else str(exc)
        print(fail("ChromaDB in-memory client thất bại", detail))
        errors += 1

    # Test NarrativeMemory
    try:
        from backend.rag.context_builder.narrative_memory import (
            NarrativeMemoryService,
        )

        print(ok("NarrativeMemory import thành công"))

    except Exception as exc:
        detail = traceback.format_exc() if verbose else str(exc)
        print(warn(f"NarrativeMemory import: {str(exc)[:100]}"))

    return errors


# ─── Section 8: File System ────────────────────────────────────────────────────

def check_filesystem() -> int:
    section("8. File System & Quyền Ghi")
    errors = 0

    root = Path(__file__).parent
    paths_to_check = [
        (root / "backend", "backend/"),
        (root / "frontend", "frontend/"),
        (root / "pyproject.toml", "pyproject.toml"),
        (root / ".env", ".env"),
        (root / "backend" / "database" / "migrations", "alembic migrations/"),
    ]

    for path, label in paths_to_check:
        if path.exists():
            print(ok(f"{label} tồn tại"))
        else:
            if label == ".env":
                print(warn(f"{label} không tồn tại"))
            else:
                print(fail(f"{label} không tồn tại"))
                errors += 1

    # Kiểm tra quyền ghi thư mục data
    test_file = root / ".debug_write_test"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        print(ok("Thư mục gốc có quyền ghi"))
    except PermissionError:
        print(fail("Thư mục gốc không có quyền ghi"))
        errors += 1

    return errors


# ─── Tổng kết ─────────────────────────────────────────────────────────────────

def print_summary(results: dict[str, int]) -> None:
    section("Tổng Kết")
    total_errors = sum(results.values())
    for name, errs in results.items():
        if errs == 0:
            print(ok(f"{name}"))
        else:
            print(fail(f"{name} — {errs} lỗi"))

    print()
    if total_errors == 0:
        print(f"  {GREEN}{BOLD}Tất cả kiểm tra thành công!{RESET}")
    else:
        print(f"  {RED}{BOLD}{total_errors} lỗi tổng cộng — xem chi tiết ở trên.{RESET}")
    print()


# ─── Main ──────────────────────────────────────────────────────────────────────

SECTIONS: dict[str, str] = {
    "env": "Môi trường",
    "db": "Database",
    "redis": "Redis",
    "llm": "LLM",
    "api": "API Server",
    "imports": "Imports",
    "vector": "ChromaDB",
    "fs": "File System",
}


def _check_venv() -> None:
    """Cảnh báo nếu không chạy trong virtualenv đúng."""
    in_venv = sys.prefix != sys.base_prefix
    root = Path(__file__).parent
    venv_python = root / "narrativeos" / "bin" / "python3"

    if not in_venv:
        print(f"\n{YELLOW}{BOLD}[CẢNH BÁO]{RESET} Bạn đang chạy bằng Python hệ thống, không phải virtualenv.")
        if venv_python.exists():
            print(f"  Hãy dùng:  {CYAN}{venv_python} debug.py{RESET}")
        else:
            print(f"  Cài dependencies trước:  {CYAN}poetry install{RESET}  hoặc  {CYAN}pip install -e .[dev]{RESET}")
        print()

    # Kiểm tra pydantic (dependency tối thiểu)
    try:
        import pydantic  # noqa: F401
    except ImportError:
        print(f"{RED}{BOLD}[LỖI]{RESET} pydantic chưa cài — dependencies chưa được cài đặt.")
        print(f"  Chạy:  {CYAN}poetry install{RESET}  để cài tất cả packages.")
        if venv_python.exists() and not in_venv:
            print(f"  Hoặc:  {CYAN}{venv_python} debug.py{RESET}  nếu đã cài qua cách khác.")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="NarrativeOS Debug Script")
    parser.add_argument("--section", choices=list(SECTIONS.keys()), help="Chỉ chạy một section cụ thể")
    parser.add_argument("--api-url", default="http://localhost:8000", help="URL API server (default: http://localhost:8000)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Hiển thị chi tiết lỗi đầy đủ")
    args = parser.parse_args()

    # Đảm bảo chạy từ thư mục gốc project
    root = Path(__file__).parent
    os.chdir(root)
    sys.path.insert(0, str(root))

    _check_venv()

    header(f"2026-06-19  |  {args.api_url}")

    results: dict[str, int] = {}

    def run(key: str) -> None:
        fn_map = {
            "env": lambda: check_environment(args.verbose),
            "db": lambda: check_database(args.verbose),
            "redis": lambda: check_redis(args.verbose),
            "llm": lambda: check_llm(args.verbose),
            "api": lambda: check_api(args.api_url, args.verbose),
            "imports": lambda: check_imports(args.verbose),
            "vector": lambda: check_vectorstore(args.verbose),
            "fs": check_filesystem,
        }
        results[SECTIONS[key]] = fn_map[key]()

    if args.section:
        run(args.section)
    else:
        for key in SECTIONS:
            run(key)

    print_summary(results)


if __name__ == "__main__":
    main()
