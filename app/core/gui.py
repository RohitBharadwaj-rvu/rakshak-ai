"""
GuardianLine Family Protection Web GUI / Dashboard (Lane C / T-DASH).
File: app/core/gui.py (Mounts at /dashboard and /gui)

Features:
- Complete XSS prevention via html.escape on all dynamic outputs
- Escapes role after title capitalization to prevent entity mutation
- Dual authentication:
    1) Master token (GUARDIAN_DASHBOARD_TOKEN) by Bearer header, or a one-time ?token= login
       that is swapped for an HttpOnly session cookie so the token never sits in links
    2) Per-call expiring signed HMAC (exp + sig, REPORT_SIGNING_SECRET) for family alert links
- Pluggable CallStore adapter (BaseCallStore); app.core.lane_c.install() points it at Lane B's store
- 1930 report rendered by Lane B's generator when installed (local fallback only when standalone)
- Sorting by parsed ISO-8601 timestamps rather than raw string comparison
- Real pagination controls (Next/Previous, total counts, no silent truncation)
- Shows verdict badges, call duration, and extracted payment/link intel on detail view
"""

import html
import logging
import os
import secrets
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.notify.alerts import get_report_signing_secret, verify_report_signature

logger = logging.getLogger("guardianline.gui")

IST = timezone(timedelta(hours=5, minutes=30))


class BaseCallStore(ABC):
    """Abstract storage interface decoupling the GUI from the specific CallRecord backend."""

    @abstractmethod
    def add_call(self, record: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def get_calls(
        self,
        verdict: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Returns (paged_calls, total_matching_count)."""
        pass

    @abstractmethod
    def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


def _parse_timestamp(record: Dict[str, Any]) -> float:
    raw = record.get("start_time") or record.get("created_at") or record.get("timestamp")
    if raw:
        if isinstance(raw, (int, float)):
            return float(raw)
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    return 0.0


class InMemoryCallStore(BaseCallStore):
    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self._calls: Dict[str, Dict[str, Any]] = {}

    def add_call(self, record: Dict[str, Any]) -> None:
        call_id = record.get("call_id")
        if not call_id:
            raise ValueError("Record must contain 'call_id'")
        with self._lock:
            self._calls[call_id] = record

    def get_calls(
        self,
        verdict: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            calls = list(self._calls.values())

        # Sort chronologically (newest first)
        calls.sort(key=_parse_timestamp, reverse=True)

        if verdict:
            v_lower = verdict.lower()
            calls = [c for c in calls if str(c.get("verdict", "")).lower() == v_lower]

        total_count = len(calls)
        start_idx = max(0, (page - 1) * limit)
        end_idx = start_idx + limit
        return calls[start_idx:end_idx], total_count

    def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._calls.get(call_id)

    def clear(self) -> None:
        with self._lock:
            self._calls.clear()


_GLOBAL_STORE: BaseCallStore = InMemoryCallStore()


# Renders the 1930 report text for a CallRecord. Set to Lane B's generator by app.core.lane_c.install().
_REPORT_RENDERER: Optional[Callable[[Dict[str, Any]], str]] = None


def set_report_renderer(renderer: Optional[Callable[[Dict[str, Any]], str]]) -> None:
    global _REPORT_RENDERER
    _REPORT_RENDERER = renderer


def get_dashboard_store() -> BaseCallStore:
    return _GLOBAL_STORE


def set_dashboard_store(store: BaseCallStore) -> None:
    global _GLOBAL_STORE
    _GLOBAL_STORE = store


router = APIRouter(tags=["dashboard"])

SESSION_COOKIE = "gl_dash"


def _master_token() -> str:
    expected = os.environ.get("GUARDIAN_DASHBOARD_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard authentication is not configured in server environment",
        )
    return expected


def _candidate_token(request: Request, token: Optional[str], authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if token:
        return token.strip()
    return request.cookies.get(SESSION_COOKIE)


def _session_redirect(request: Request, token: str) -> RedirectResponse:
    """Swap a ?token= login for an HttpOnly cookie so the token leaves the URL bar and history."""
    params = [(k, v) for k, v in request.query_params.multi_items() if k != "token"]
    target = request.url.path + (f"?{urlencode(params)}" if params else "")
    resp = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=7 * 86400,
    )
    return resp


def verify_overview_auth(
    request: Request,
    token: Optional[str] = Query(None, description="One-time login: exchanged for a session cookie"),
    authorization: Optional[str] = Header(None, description="Bearer token authentication header"),
) -> str:
    """Verifies the master GUARDIAN_DASHBOARD_TOKEN (header, ?token= or session cookie)."""
    expected = _master_token()
    candidate = _candidate_token(request, token, authorization)
    if not candidate or not secrets.compare_digest(candidate, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid or missing dashboard token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return candidate


def verify_call_access(
    request: Request,
    call_id: str,
    token: Optional[str] = Query(None),
    exp: Optional[int] = Query(None),
    sig: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
) -> str:
    """
    Authorizes access to one call. Returns the query string that later links on the page
    must carry: the signed exp/sig for a family alert link, or "" for a logged-in session.
    """
    signing_secret = get_report_signing_secret()
    if exp is not None and sig and signing_secret:
        if verify_report_signature(call_id, exp, sig, signing_secret):
            return f"?{urlencode({'exp': exp, 'sig': sig})}"

    expected = _master_token()
    candidate = _candidate_token(request, token, authorization)
    if candidate and secrets.compare_digest(candidate, expected):
        return ""

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: invalid master token or expired call authorization link",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _safe_duration(val: Any) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


@router.get("/dashboard", response_class=HTMLResponse)
@router.get("/dashboard/", response_class=HTMLResponse)
@router.get("/gui", response_class=HTMLResponse)
@router.get("/gui/", response_class=HTMLResponse)
def render_dashboard(
    request: Request,
    auth_token: str = Depends(verify_overview_auth),
    token: Optional[str] = Query(None),
    verdict: Optional[str] = Query(None, pattern="^(scam|genuine|unsure)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    if token:
        return _session_redirect(request, auth_token)

    calls, total_calls = store.get_calls(verdict=verdict, page=page, limit=limit)

    total_pages = max(1, (total_calls + limit - 1) // limit) if total_calls > 0 else 1
    start_num = (page - 1) * limit + 1 if total_calls > 0 else 0
    end_num = min(page * limit, total_calls)

    if not calls:
        cards_html = """
        <div class="empty-state">
            <div class="empty-icon">🛡️</div>
            <h3>No calls handled yet</h3>
            <p>Elder protection is active. New screened calls will appear here in real-time.</p>
        </div>
        """
    else:
        cards_list = []
        for c in calls:
            c_id = html.escape(str(c.get("call_id", "")))
            c_path = html.escape(quote(str(c.get("call_id", "")), safe=""))
            caller = html.escape(str(c.get("caller_number") or "Unknown / Withheld"))
            v = str(c.get("verdict", "unsure")).lower()
            if v not in ("scam", "genuine", "unsure"):
                v = "unsure"

            duration_num = _safe_duration(c.get("duration"))
            summary = html.escape(str(c.get("summary") or "No summary recorded."))
            intel = c.get("extracted_intel", {}) or {}

            badge_class = "badge-scam" if v == "scam" else ("badge-genuine" if v == "genuine" else "badge-unsure")
            badge_text = "🚨 SUSPECTED SCAM" if v == "scam" else ("✅ GENUINE" if v == "genuine" else "❓ UNSURE")

            intel_items = []
            for upi in intel.get("upi_ids", []):
                intel_items.append(f'<span class="intel-tag upi">UPI: {html.escape(str(upi))}</span>')
            for acc in intel.get("bank_accounts", []):
                intel_items.append(f'<span class="intel-tag acc">A/C: {html.escape(str(acc))}</span>')
            for ifsc in intel.get("ifsc_codes", []):
                intel_items.append(f'<span class="intel-tag ifsc">IFSC: {html.escape(str(ifsc))}</span>')
            for ph in intel.get("phone_numbers", []):
                intel_items.append(f'<span class="intel-tag ph">Ph: {html.escape(str(ph))}</span>')
            for lnk in intel.get("links", []):
                intel_items.append(f'<span class="intel-tag lnk">Link: {html.escape(str(lnk))}</span>')

            intel_html = " ".join(intel_items) if intel_items else "<span class='text-muted'>No attacker payment intel extracted</span>"

            card = f"""
            <div class="call-card {v}">
                <div class="card-header">
                    <span class="badge {badge_class}">{badge_text}</span>
                    <span class="duration">{duration_num:.0f}s</span>
                </div>
                <div class="caller-number">{caller}</div>
                <div class="summary">{summary}</div>
                <div class="intel-box">{intel_html}</div>
                <div class="card-footer">
                    <span class="call-id">ID: {c_id}</span>
                    <div class="actions">
                        <a href="/dashboard/calls/{c_path}" class="btn-detail">Inspect</a>
                        <a href="/dashboard/report/{c_path}" class="btn-dossier" target="_blank">Draft 1930 report</a>
                    </div>
                </div>
            </div>
            """
            cards_list.append(card)
        cards_html = "\n".join(cards_list)

    # Build pagination controls
    token_q = ""
    verdict_q = f"&verdict={verdict}" if verdict else ""

    prev_link = f'<a href="/dashboard?page={page-1}&limit={limit}{verdict_q}{token_q}" class="btn-page">← Previous</a>' if page > 1 else '<span class="btn-page disabled">← Previous</span>'
    next_link = f'<a href="/dashboard?page={page+1}&limit={limit}{verdict_q}{token_q}" class="btn-page">Next →</a>' if page < total_pages else '<span class="btn-page disabled">Next →</span>'

    pagination_html = f"""
    <div class="pagination-bar">
        <div class="page-info">Showing {start_num}–{end_num} of {total_calls} calls (Page {page} of {total_pages})</div>
        <div class="page-buttons">
            {prev_link}
            {next_link}
        </div>
    </div>
    """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GuardianLine · Family Protection Dashboard</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            line-height: 1.5;
            padding: 16px;
            max-width: 100%;
            overflow-x: hidden;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            width: 100%;
        }}
        header {{
            margin-bottom: 24px;
            border-bottom: 1px solid #1e293b;
            padding-bottom: 16px;
        }}
        h1 {{ font-size: 20px; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 8px; }}
        .subtitle {{ font-size: 13px; color: #94a3b8; margin-top: 4px; }}
        .call-card {{
            background: #1e293b;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
            border-left: 4px solid #64748b;
            max-width: 100%;
            word-wrap: break-word;
        }}
        .call-card.scam {{ border-left-color: #ef4444; }}
        .call-card.genuine {{ border-left-color: #22c55e; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .badge {{ font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; text-transform: uppercase; }}
        .badge-scam {{ background: #7f1d1d; color: #fca5a5; }}
        .badge-genuine {{ background: #14532d; color: #86efac; }}
        .badge-unsure {{ background: #374151; color: #d1d5db; }}
        .duration {{ font-size: 12px; color: #94a3b8; }}
        .caller-number {{ font-size: 18px; font-weight: 600; color: #ffffff; margin-bottom: 6px; }}
        .summary {{ font-size: 14px; color: #cbd5e1; margin-bottom: 12px; }}
        .intel-box {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
        .intel-tag {{ font-size: 12px; padding: 3px 8px; border-radius: 4px; font-family: monospace; }}
        .intel-tag.upi {{ background: #312e81; color: #c7d2fe; }}
        .intel-tag.acc {{ background: #064e3b; color: #a7f3d0; }}
        .intel-tag.ifsc {{ background: #14532d; color: #bbf7d0; }}
        .intel-tag.ph {{ background: #701a75; color: #f5d0fe; }}
        .intel-tag.lnk {{ background: #831843; color: #fbcfe8; }}
        .text-muted {{ font-size: 12px; color: #64748b; font-style: italic; }}
        .card-footer {{ display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #334155; padding-top: 10px; }}
        .call-id {{ font-size: 11px; color: #64748b; font-family: monospace; }}
        .actions {{ display: flex; gap: 8px; }}
        .btn-detail {{
            font-size: 12px;
            background: #334155;
            color: #f1f5f9;
            text-decoration: none;
            padding: 6px 10px;
            border-radius: 6px;
            font-weight: 500;
        }}
        .btn-dossier {{
            font-size: 12px;
            background: #2563eb;
            color: #ffffff;
            text-decoration: none;
            padding: 6px 12px;
            border-radius: 6px;
            font-weight: 600;
        }}
        .pagination-bar {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 12px;
            margin-top: 24px;
            margin-bottom: 32px;
            padding: 16px;
            background: #1e293b;
            border-radius: 8px;
        }}
        .page-info {{ font-size: 13px; color: #94a3b8; }}
        .page-buttons {{ display: flex; gap: 12px; }}
        .btn-page {{
            font-size: 13px;
            background: #2563eb;
            color: white;
            text-decoration: none;
            padding: 6px 16px;
            border-radius: 6px;
            font-weight: 600;
        }}
        .btn-page.disabled {{
            background: #334155;
            color: #64748b;
            pointer-events: none;
        }}
        .empty-state {{
            text-align: center;
            padding: 48px 16px;
            background: #1e293b;
            border-radius: 12px;
            margin-top: 24px;
        }}
        .empty-icon {{ font-size: 40px; margin-bottom: 12px; }}
        .empty-state h3 {{ font-size: 16px; margin-bottom: 8px; color: #e2e8f0; }}
        .empty-state p {{ font-size: 13px; color: #94a3b8; }}

        @media (max-width: 360px) {{
            body {{ padding: 10px; }}
            h1 {{ font-size: 18px; }}
            .caller-number {{ font-size: 16px; }}
            .btn-detail, .btn-dossier {{ padding: 4px 8px; font-size: 11px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🛡️ GuardianLine Shield</h1>
            <div class="subtitle">Calls handled by GuardianLine for your family</div>
        </header>
        <main>
            {cards_html}
            {pagination_html}
        </main>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@router.get("/dashboard/calls/{call_id}", response_class=HTMLResponse)
def render_call_detail(
    call_id: str,
    auth: str = Depends(verify_call_access),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    # Signed family links open one call only, so they get no link back to the full list
    back_link = "" if auth else '<a href="/dashboard" class="back-link">← Back to Overview</a>'
    record = store.get_call(call_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call record '{call_id}' not found",
        )

    caller = html.escape(str(record.get("caller_number") or "Unknown"))
    v = str(record.get("verdict", "unsure")).lower()
    summary = html.escape(str(record.get("summary") or "No summary recorded."))
    duration = _safe_duration(record.get("duration"))
    transcript = record.get("transcript", []) or []
    intel = record.get("extracted_intel", {}) or {}

    badge_class = "badge-scam" if v == "scam" else ("badge-genuine" if v == "genuine" else "badge-unsure")
    badge_text = "🚨 SUSPECTED SCAM" if v == "scam" else ("✅ GENUINE" if v == "genuine" else "❓ UNSURE")

    intel_items = []
    for upi in intel.get("upi_ids", []):
        intel_items.append(f'<span class="intel-tag upi">UPI: {html.escape(str(upi))}</span>')
    for acc in intel.get("bank_accounts", []):
        intel_items.append(f'<span class="intel-tag acc">A/C: {html.escape(str(acc))}</span>')
    for ifsc in intel.get("ifsc_codes", []):
        intel_items.append(f'<span class="intel-tag ifsc">IFSC: {html.escape(str(ifsc))}</span>')
    for ph in intel.get("phone_numbers", []):
        intel_items.append(f'<span class="intel-tag ph">Ph: {html.escape(str(ph))}</span>')
    for lnk in intel.get("links", []):
        intel_items.append(f'<span class="intel-tag lnk">Link: {html.escape(str(lnk))}</span>')

    intel_html = " ".join(intel_items) if intel_items else "<span class='text-muted'>No attacker payment intel extracted</span>"

    turns_html = []
    for turn in transcript:
        raw_role = str(turn.get("role", "unknown"))
        escaped_role = html.escape(raw_role.title())
        content = html.escape(str(turn.get("content", "")))
        role_class = "caller-turn" if raw_role.lower() in ("caller", "user") else "agent-turn"
        turns_html.append(f'<div class="transcript-turn {role_class}"><strong>{escaped_role}:</strong> {content}</div>')

    transcript_content = "\n".join(turns_html) if turns_html else "<div class='text-muted'>No dialogue turns recorded.</div>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Call Details · {html.escape(call_id)}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            padding: 16px;
            max-width: 100%;
            overflow-x: hidden;
        }}
        .container {{ max-width: 600px; margin: 0 auto; }}
        .back-link {{ display: inline-block; color: #38bdf8; text-decoration: none; margin-bottom: 16px; font-size: 14px; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
        h2 {{ font-size: 18px; margin-bottom: 12px; color: #e2e8f0; }}
        .badge {{ font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; text-transform: uppercase; }}
        .badge-scam {{ background: #7f1d1d; color: #fca5a5; }}
        .badge-genuine {{ background: #14532d; color: #86efac; }}
        .badge-unsure {{ background: #374151; color: #d1d5db; }}
        .caller {{ font-size: 20px; font-weight: bold; margin-top: 8px; margin-bottom: 8px; }}
        .summary {{ font-size: 14px; color: #cbd5e1; margin-bottom: 16px; }}
        .intel-box {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }}
        .intel-tag {{ font-size: 12px; padding: 3px 8px; border-radius: 4px; font-family: monospace; }}
        .intel-tag.upi {{ background: #312e81; color: #c7d2fe; }}
        .intel-tag.acc {{ background: #064e3b; color: #a7f3d0; }}
        .intel-tag.ifsc {{ background: #14532d; color: #bbf7d0; }}
        .intel-tag.ph {{ background: #701a75; color: #f5d0fe; }}
        .intel-tag.lnk {{ background: #831843; color: #fbcfe8; }}
        .transcript-turn {{ padding: 8px 12px; border-radius: 8px; margin-bottom: 8px; font-size: 14px; }}
        .caller-turn {{ background: #334155; }}
        .agent-turn {{ background: #1e3a8a; }}
        .btn-dossier {{
            display: inline-block;
            background: #2563eb;
            color: white;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        {back_link}
        <div class="card">
            <div><span class="badge {badge_class}">{badge_text}</span></div>
            <div class="caller">{caller}</div>
            <div class="summary">{summary}</div>
            <div class="intel-box">{intel_html}</div>
            <a href="/dashboard/report/{html.escape(quote(call_id, safe=''))}{html.escape(auth)}" class="btn-dossier" target="_blank">Download draft 1930 report</a>
        </div>
        <div class="card">
            <h2>Call Transcript ({duration:.0f}s)</h2>
            {transcript_content}
        </div>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@router.get("/dashboard/api/calls", response_model=List[Dict[str, Any]])
def list_calls_api(
    auth_token: str = Depends(verify_overview_auth),
    verdict: Optional[str] = Query(None, pattern="^(scam|genuine|unsure)$", description="Filter: scam, genuine, unsure"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    calls, _ = store.get_calls(verdict=verdict, page=page, limit=limit)
    return calls


@router.get("/dashboard/api/calls/{call_id}", response_model=Dict[str, Any])
def get_call_api(
    call_id: str,
    auth: str = Depends(verify_call_access),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    record = store.get_call(call_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call record with ID '{call_id}' not found",
        )
    return record


@router.get("/dashboard/report/{call_id}")
def download_1930_report(
    call_id: str,
    auth: str = Depends(verify_call_access),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    record = store.get_call(call_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call record '{call_id}' not found",
        )

    safe_name = "".join(ch for ch in call_id if ch.isalnum() or ch in "-_")[:64] or "call"
    headers = {
        "Content-Disposition": f"inline; filename=1930_report_{safe_name}.txt",
        "X-Content-Type-Options": "nosniff",
    }

    # Lane B owns the 1930 report (T-RPT, golden-file tested). Use it whenever it is installed.
    if _REPORT_RENDERER is not None:
        return Response(content=_REPORT_RENDERER(record), media_type="text/plain; charset=utf-8", headers=headers)

    # Standalone fallback only (lane C running without lane B's backend)
    caller = record.get("caller_number") or "Not captured"
    intel = record.get("extracted_intel", {}) or {}
    upi_str = ", ".join(intel.get("upi_ids", [])) or "Not captured"
    acc_str = ", ".join(intel.get("bank_accounts", [])) or "Not captured"
    ifsc_str = ", ".join(intel.get("ifsc_codes", [])) or "Not captured"
    ph_str = ", ".join(intel.get("phone_numbers", [])) or "Not captured"
    lnk_str = ", ".join(intel.get("links", [])) or "Not captured"
    summary = record.get("summary") or "Not captured"
    duration = _safe_duration(record.get("duration"))

    created_raw = record.get("start_time") or record.get("created_at") or record.get("timestamp")
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    if created_raw:
        try:
            dt = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            incident_time_ist = dt.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        except Exception:
            incident_time_ist = str(created_raw)
    else:
        incident_time_ist = now_ist

    report_text = f"""================================================================================
NATIONAL CYBERCRIME REPORTING PORTAL (1930 / cybercrime.gov.in)
PRE-FILLED INCIDENT DOSSIER
================================================================================
INCIDENT DETAILS:
- Case Reference ID: {call_id}
- Incident Date & Time: {incident_time_ist}
- Call Duration: {duration:.1f} seconds
- Suspect Telephony Number: {caller}
- Attack Category: Telecom Impersonation / Voice Phishing (Vishing)
- Suspect UPI Handles: {upi_str}
- Suspect Bank Account(s): {acc_str}
- Suspect IFSC Code(s): {ifsc_str}
- Associated Callback Number(s): {ph_str}
- Associated Phishing Links: {lnk_str}

NARRATIVE SUMMARY:
{summary}

VERIFICATION NOTE FOR FAMILY:
Please review and verify the above captured evidence with the elder before
formal submission to the National Cybercrime Reporting Portal (1930).
================================================================================
Generated by GuardianLine Autonomous Protection System
"""
    return Response(content=report_text, media_type="text/plain; charset=utf-8", headers=headers)
