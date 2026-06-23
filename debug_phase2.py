#!/usr/bin/env python3
"""
NarrativeOS Debug Phase 2 — Auth + CRUD Test Suite
Kiểm tra toàn bộ luồng: register → login → JWT → project CRUD → isolation → cleanup.

Cách dùng:
    python3 debug_phase2.py                          # Tất cả tests, API tại localhost:8000
    python3 debug_phase2.py --api http://host:8000   # Custom API URL
    python3 debug_phase2.py --keep                   # Giữ lại data test sau khi chạy
    python3 debug_phase2.py --section auth           # Chỉ chạy section auth
    python3 debug_phase2.py --section projects       # Chỉ chạy section projects
    python3 debug_phase2.py --section isolation      # Chỉ chạy test ownership isolation
    python3 debug_phase2.py -v                       # Verbose: in response body đầy đủ
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# ─── Terminal colors ───────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"

OK   = f"{GREEN}✓{RESET}"
FAIL = f"{RED}✗{RESET}"
WARN = f"{YELLOW}⚠{RESET}"
INFO = f"{CYAN}ℹ{RESET}"

_pass_count = 0
_fail_count = 0


def ok(msg: str, detail: str = "") -> None:
    global _pass_count
    _pass_count += 1
    line = f"  {OK}  {msg}"
    if detail:
        line += f"  {DIM}({detail}){RESET}"
    print(line)


def fail(msg: str, detail: str = "") -> None:
    global _fail_count
    _fail_count += 1
    line = f"  {FAIL}  {msg}"
    if detail:
        line += f"\n{DIM}       {detail}{RESET}"
    print(line)


def warn(msg: str) -> None:
    print(f"  {WARN}  {msg}")


def info(msg: str) -> None:
    print(f"  {INFO}  {msg}")


def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─' * 62}{RESET}")
    print(f"{BOLD}{CYAN} {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 62}{RESET}")


def header() -> None:
    print(f"\n{BOLD}{'═' * 62}{RESET}")
    print(f"{BOLD}  NarrativeOS  Phase 2  —  Auth + CRUD Test Suite{RESET}")
    print(f"{BOLD}{'═' * 62}{RESET}")


# ─── HTTP client ───────────────────────────────────────────────────────────────

class APIClient:
    def __init__(self, base_url: str, token: str | None = None, verbose: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.verbose = verbose

    def with_token(self, token: str) -> "APIClient":
        return APIClient(self.base_url, token=token, verbose=self.verbose)

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        expected_status: int | None = None,
    ) -> tuple[int, Any]:
        url = self.base_url + path
        data = json.dumps(body).encode() if body is not None else None
        headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=8) as resp:
                raw = resp.read().decode("utf-8")
                status = resp.status
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            status = exc.code
        except URLError as exc:
            raise ConnectionError(f"Không kết nối được {url}: {exc}") from exc

        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw

        if self.verbose:
            body_str = json.dumps(parsed, ensure_ascii=False, indent=2) if isinstance(parsed, (dict, list)) else str(parsed)
            print(f"{DIM}       → {method} {path}  status={status}{RESET}")
            for line in body_str.splitlines()[:12]:
                print(f"{DIM}         {line}{RESET}")

        return status, parsed

    def get(self, path: str, **kw: Any) -> tuple[int, Any]:
        return self.request("GET", path, **kw)

    def post(self, path: str, body: dict[str, Any] | None = None, **kw: Any) -> tuple[int, Any]:
        return self.request("POST", path, body=body, **kw)

    def patch(self, path: str, body: dict[str, Any], **kw: Any) -> tuple[int, Any]:
        return self.request("PATCH", path, body=body, **kw)

    def delete(self, path: str, **kw: Any) -> tuple[int, Any]:
        return self.request("DELETE", path, **kw)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def assert_status(label: str, got: int, want: int, body: Any = None) -> bool:
    if got == want:
        ok(label, f"HTTP {got}")
        return True
    detail = ""
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("message") or json.dumps(body, ensure_ascii=False)[:120]
    elif isinstance(body, str):
        detail = body[:120]
    fail(label, f"expected {want}, got {got}  —  {detail}")
    return False


def assert_field(label: str, obj: Any, field: str, expected: Any = None) -> bool:
    if not isinstance(obj, dict):
        fail(label, f"Response không phải dict: {type(obj)}")
        return False
    if field not in obj:
        fail(label, f"Thiếu field '{field}' trong response")
        return False
    val = obj[field]
    if expected is not None and val != expected:
        fail(label, f"'{field}' = {val!r}, mong đợi {expected!r}")
        return False
    ok(label, f"{field}={val!r}" if expected is None else "")
    return True


# ─── Section A: Kiểm tra server sống ──────────────────────────────────────────

def check_server(client: APIClient) -> bool:
    section("A. Server Connectivity")
    try:
        status, body = client.get("/")
        if assert_status("GET / → 200", status, 200, body):
            msg = body.get("message", "") if isinstance(body, dict) else ""
            info(f"Server: {msg}")
            return True
        return False
    except ConnectionError as exc:
        fail("Không thể kết nối server", str(exc))
        fail("Hãy chắc chắn server đang chạy: python3 -m backend.main")
        return False


# ─── Section B: Auth ───────────────────────────────────────────────────────────

class Credentials:
    def __init__(self, username: str, password: str, token: str, user_id: str) -> None:
        self.username = username
        self.password = password
        self.token = token
        self.user_id = user_id


def check_auth(client: APIClient, suffix: str = "") -> Credentials | None:
    section(f"B. Auth Flow{' (' + suffix + ')' if suffix else ''}")

    username = _uid(f"testuser_{suffix}_" if suffix else "testuser_")
    password = "SecurePass123!"
    email = f"{username}@test.local"

    # Register
    status, body = client.post("/auth/register", {
        "username": username,
        "password": password,
        "email": email,
        "display_name": f"Test User {suffix}",
    })
    if not assert_status(f"POST /auth/register ({username})", status, 200, body):
        return None
    if not assert_field("  access_token tồn tại", body, "access_token"):
        return None
    token = body["access_token"]
    user_id = body.get("user", {}).get("id", "")
    ok(f"  user_id = {user_id}")

    authed = client.with_token(token)

    # Không token → 401
    status, body = client.get("/auth/me")
    assert_status("GET /auth/me không có token → 401", status, 401, body)

    # Có token → 200
    status, body = authed.get("/auth/me")
    if assert_status("GET /auth/me với token → 200", status, 200, body):
        assert_field("  username đúng", body, "username", username)

    # Login
    status, body = client.post("/auth/login", {"username": username, "password": password})
    assert_status("POST /auth/login → 200", status, 200, body)

    # Sai password → 401
    status, body = client.post("/auth/login", {"username": username, "password": "wrongpass"})
    assert_status("POST /auth/login sai password → 401", status, 401, body)

    # Đăng ký username trùng → 409
    status, body = client.post("/auth/register", {"username": username, "password": password})
    assert_status("POST /auth/register trùng username → 409", status, 409, body)

    return Credentials(username=username, password=password, token=token, user_id=user_id)


# ─── Section C: Project CRUD ──────────────────────────────────────────────────

def check_projects(client: APIClient, creds: Credentials, verbose: bool = False) -> list[str]:
    """Trả về danh sách project_id đã tạo (để cleanup)."""
    section("C. Project CRUD")
    authed = client.with_token(creds.token)
    created_ids: list[str] = []

    # Không token → 401
    status, body = client.get("/projects")
    assert_status("GET /projects không có token → 401", status, 401, body)

    # List rỗng ban đầu
    status, body = authed.get("/projects")
    if assert_status("GET /projects (list rỗng) → 200", status, 200, body):
        if isinstance(body, list):
            ok(f"  Danh sách ban đầu: {len(body)} project(s)")

    # CREATE
    title1 = f"Novel Alpha {_uid()}"
    status, body = authed.post("/projects", {"title": title1, "description": "Dự án thử nghiệm A"})
    if assert_status(f"POST /projects (tạo '{title1}') → 201", status, 201, body):
        assert_field("  id tồn tại", body, "id")
        assert_field("  title đúng", body, "title", title1)
        assert_field("  status = draft", body, "status", "draft")
        pid1 = body.get("id", "")
        created_ids.append(pid1)
        ok(f"  project_id = {pid1}")

    # CREATE thứ 2
    title2 = f"Novel Beta {_uid()}"
    status, body = authed.post("/projects", {"title": title2})
    if assert_status(f"POST /projects (tạo '{title2}') → 201", status, 201, body):
        pid2 = body.get("id", "")
        created_ids.append(pid2)

    # Tạo title trùng → 409
    status, body = authed.post("/projects", {"title": title1})
    assert_status("POST /projects title trùng → 409", status, 409, body)

    # LIST — phải thấy 2 project vừa tạo
    status, body = authed.get("/projects")
    if assert_status("GET /projects → 200", status, 200, body) and isinstance(body, list):
        ids_in_list = {p.get("id") for p in body if isinstance(p, dict)}
        if all(pid in ids_in_list for pid in created_ids):
            ok(f"  List trả về đúng {len(created_ids)} projects vừa tạo")
        else:
            fail("  Một số project vừa tạo không xuất hiện trong list")

    # GET by ID
    if created_ids:
        pid1 = created_ids[0]
        status, body = authed.get(f"/projects/{pid1}")
        if assert_status(f"GET /projects/{pid1[:8]}... → 200", status, 200, body):
            assert_field("  title đúng", body, "title", title1)

    # PATCH
    if created_ids:
        pid1 = created_ids[0]
        new_title = f"Novel Alpha Revised {_uid()}"
        status, body = authed.patch(f"/projects/{pid1}", {"title": new_title, "description": "Updated"})
        if assert_status(f"PATCH /projects/{pid1[:8]}... → 200", status, 200, body):
            assert_field("  title đã đổi", body, "title", new_title)
            assert_field("  description đã đổi", body, "description", "Updated")

    # PATCH status → active
    if created_ids:
        pid1 = created_ids[0]
        status, body = authed.patch(f"/projects/{pid1}", {"status": "active"})
        assert_status("PATCH status → active → 200", status, 200, body)

    # GET không tồn tại → 404
    status, body = authed.get("/projects/nonexistent-id-xyz")
    assert_status("GET /projects/<invalid_id> → 404", status, 404, body)

    # DELETE
    if len(created_ids) >= 2:
        pid2 = created_ids[-1]
        status, body = authed.delete(f"/projects/{pid2}")
        if assert_status(f"DELETE /projects/{pid2[:8]}... → 200", status, 200, body):
            assert_field("  status = deleted", body, "status", "deleted")
            created_ids.remove(pid2)

        # Verify đã xóa → 404
        status, body = authed.get(f"/projects/{pid2}")
        assert_status(f"GET project đã xóa → 404", status, 404, body)

    return created_ids


# ─── Section D: Ownership Isolation ───────────────────────────────────────────

def check_isolation(client: APIClient, creds_a: Credentials, creds_b: Credentials) -> None:
    section("D. Ownership Isolation (User A vs User B)")

    authed_a = client.with_token(creds_a.token)
    authed_b = client.with_token(creds_b.token)

    # A tạo project
    title = f"Private Project {_uid()}"
    status, body = authed_a.post("/projects", {"title": title})
    if not assert_status("User A tạo project → 201", status, 201, body):
        return
    pid = body.get("id", "")
    ok(f"  project_id = {pid}")

    # B list → không thấy project của A
    status, body = authed_b.get("/projects")
    if assert_status("User B GET /projects → 200", status, 200, body) and isinstance(body, list):
        ids = {p.get("id") for p in body}
        if pid not in ids:
            ok("User B KHÔNG thấy project của User A  (isolation đúng)")
        else:
            fail("User B THẤY project của User A  (BUG: ownership không hoạt động!)")

    # B GET trực tiếp → 404
    status, body = authed_b.get(f"/projects/{pid}")
    assert_status("User B GET project của A → 404", status, 404, body)

    # B PATCH project của A → 404
    status, body = authed_b.patch(f"/projects/{pid}", {"description": "Hacked!"})
    assert_status("User B PATCH project của A → 404", status, 404, body)

    # B DELETE project của A → 404
    status, body = authed_b.delete(f"/projects/{pid}")
    assert_status("User B DELETE project của A → 404", status, 404, body)

    # A xóa project của chính mình → OK
    status, body = authed_a.delete(f"/projects/{pid}")
    assert_status("User A DELETE project của mình → 200", status, 200, body)


# ─── Section E: Cleanup ────────────────────────────────────────────────────────

def cleanup(client: APIClient, creds: Credentials, project_ids: list[str]) -> None:
    section("E. Cleanup")
    authed = client.with_token(creds.token)
    for pid in project_ids:
        status, _ = authed.delete(f"/projects/{pid}")
        if status == 200:
            ok(f"Đã xóa project {pid[:8]}...")
        elif status == 404:
            info(f"Project {pid[:8]}... không tồn tại (đã xóa trước đó)")
        else:
            warn(f"Không xóa được project {pid[:8]}... (status={status})")
    info("User test accounts không bị xóa (API chưa có DELETE /auth/user endpoint)")


# ─── Tổng kết ──────────────────────────────────────────────────────────────────

def print_summary() -> None:
    global _pass_count, _fail_count
    total = _pass_count + _fail_count
    print(f"\n{BOLD}{'═' * 62}{RESET}")
    print(f"{BOLD}  Kết quả: {_pass_count}/{total} kiểm tra thành công{RESET}")
    if _fail_count == 0:
        print(f"  {GREEN}{BOLD}Tất cả tests pass!{RESET}")
    else:
        print(f"  {RED}{BOLD}{_fail_count} test(s) FAIL — xem chi tiết ở trên.{RESET}")
    print(f"{BOLD}{'═' * 62}{RESET}\n")


# ─── Main ──────────────────────────────────────────────────────────────────────

SECTIONS = {"auth", "projects", "isolation"}


def main() -> None:
    parser = argparse.ArgumentParser(description="NarrativeOS Phase 2 Debug — Auth + CRUD Tests")
    parser.add_argument("--api", default="http://localhost:8000", help="Base URL API server")
    parser.add_argument("--keep", action="store_true", help="Giữ lại data test (không cleanup)")
    parser.add_argument("--section", choices=sorted(SECTIONS), help="Chỉ chạy một section")
    parser.add_argument("--verbose", "-v", action="store_true", help="In response body đầy đủ")
    args = parser.parse_args()

    header()
    info(f"API: {args.api}")
    info(f"Verbose: {args.verbose}")

    client = APIClient(args.api, verbose=args.verbose)

    # Ping server trước
    if not check_server(client):
        print_summary()
        sys.exit(1)

    run_all = args.section is None

    # Auth Section
    creds_a: Credentials | None = None
    creds_b: Credentials | None = None

    if run_all or args.section == "auth":
        creds_a = check_auth(client, suffix="A")
        if run_all:
            creds_b = check_auth(client, suffix="B")

    # Cần creds để chạy projects/isolation
    if (run_all or args.section in {"projects", "isolation"}) and creds_a is None:
        info("Tạo user tạm để chạy section này...")
        creds_a = check_auth(client, suffix="A")

    # Projects CRUD
    remaining_ids: list[str] = []
    if (run_all or args.section == "projects") and creds_a:
        remaining_ids = check_projects(client, creds_a, verbose=args.verbose)

    # Isolation
    if (run_all or args.section == "isolation"):
        if creds_a is None:
            fail("Cần creds_a để test isolation")
        elif creds_b is None:
            info("Tạo User B để test isolation...")
            creds_b = check_auth(client, suffix="B")

        if creds_a and creds_b:
            check_isolation(client, creds_a, creds_b)

    # Cleanup
    if not args.keep and creds_a and remaining_ids:
        cleanup(client, creds_a, remaining_ids)
    elif args.keep:
        info(f"--keep: giữ lại {len(remaining_ids)} project(s)")

    print_summary()
    sys.exit(0 if _fail_count == 0 else 1)


if __name__ == "__main__":
    main()
