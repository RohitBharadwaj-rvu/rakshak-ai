"""
GuardianLine Family Protection Web GUI / Dashboard (Lane C / T-DASH).
File: app/core/gui.py (Mounts at /dashboard and /gui)

Features:
- Complete XSS prevention via html.escape on all dynamic outputs
- Timing-attack-safe authentication using secrets.compare_digest
- Refuses to authenticate when GUARDIAN_DASHBOARD_TOKEN is unset
- Mobile-responsive layout strictly compliant with 360px+ screen widths
- Paginated call list and detailed transcript inspection
"""

import html
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse

import threading

class InMemoryCallStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._calls: Dict[str, Dict[str, Any]] = {}

    def add_call(self, record: Dict[str, Any]) -> None:
        call_id = record.get("call_id")
        if not call_id:
            raise ValueError("Record must contain 'call_id'")
        with self._lock:
            self._calls[call_id] = record

    def get_calls(self, verdict: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            calls = list(self._calls.values())
        calls.sort(key=lambda x: str(x.get("created_at") or x.get("timestamp") or x.get("call_id") or ""), reverse=True)
        if verdict:
            v_lower = verdict.lower()
            calls = [c for c in calls if str(c.get("verdict", "")).lower() == v_lower]
        return calls[:limit]

    def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._calls.get(call_id)

    def clear(self) -> None:
        with self._lock:
            self._calls.clear()


_GLOBAL_STORE = InMemoryCallStore()


def get_dashboard_store() -> InMemoryCallStore:
    return _GLOBAL_STORE


router = APIRouter(tags=["dashboard"])

IST = timezone(timedelta(hours=5, minutes=30))


def verify_dashboard_auth(
    token: Optional[str] = Query(None, description="Dashboard auth token query parameter"),
    authorization: Optional[str] = Header(None, description="Bearer token authentication header"),
) -> str:
    """
    Verifies authentication token using timing-safe comparison.
    Fails safely if GUARDIAN_DASHBOARD_TOKEN is not configured in environment.
    """
    expected_token = os.environ.get("GUARDIAN_DASHBOARD_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard authentication is not configured in server environment",
        )

    candidate_token = None
    if authorization and authorization.lower().startswith("bearer "):
        candidate_token = authorization[7:].strip()
    elif token:
        candidate_token = token.strip()

    if not candidate_token or not secrets.compare_digest(candidate_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid or missing dashboard token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return candidate_token


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
    auth_token: str = Depends(verify_dashboard_auth),
    verdict: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    store: InMemoryCallStore = Depends(get_dashboard_store),
):
    all_calls = store.get_calls(verdict=verdict, limit=1000)
    total_calls = len(all_calls)

    start_idx = (page - 1) * limit
    calls = all_calls[start_idx : start_idx + limit]

    if not calls:
        cards_html = """
        <div class="empty-state">
            <div class="empty-icon">🛡️</div>
            <h3>No suspicious calls intercepted yet</h3>
            <p>Elder protection is active. New screened calls will appear here in real-time.</p>
        </div>
        """
    else:
        cards_list = []
        for c in calls:
            c_id = html.escape(str(c.get("call_id", "")))
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
                        <a href="/dashboard/calls/{c_id}?token={html.escape(auth_token)}" class="btn-detail">Inspect</a>
                        <a href="/dashboard/report/{c_id}?token={html.escape(auth_token)}" class="btn-dossier" target="_blank">1930 Dossier</a>
                    </div>
                </div>
            </div>
            """
            cards_list.append(card)
        cards_html = "\n".join(cards_list)

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
            <div class="subtitle">Autonomous Voice Screening &amp; Honeypot Protection</div>
        </header>
        <main>
            {cards_html}
        </main>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@router.get("/dashboard/calls/{call_id}", response_class=HTMLResponse)
def render_call_detail(
    call_id: str,
    auth_token: str = Depends(verify_dashboard_auth),
    store: InMemoryCallStore = Depends(get_dashboard_store),
):
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

    turns_html = []
    for turn in transcript:
        role = html.escape(str(turn.get("role", "unknown")))
        content = html.escape(str(turn.get("content", "")))
        role_class = "caller-turn" if role in ("caller", "user") else "agent-turn"
        turns_html.append(f'<div class="transcript-turn {role_class}"><strong>{role.title()}:</strong> {content}</div>')

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
        .caller {{ font-size: 20px; font-weight: bold; margin-bottom: 8px; }}
        .summary {{ font-size: 14px; color: #cbd5e1; margin-bottom: 16px; }}
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
        <a href="/dashboard?token={html.escape(auth_token)}" class="back-link">← Back to Overview</a>
        <div class="card">
            <div class="caller">{caller}</div>
            <div class="summary">{summary}</div>
            <a href="/dashboard/report/{html.escape(call_id)}?token={html.escape(auth_token)}" class="btn-dossier" target="_blank">Download Pre-Filled 1930 Dossier</a>
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
    auth_token: str = Depends(verify_dashboard_auth),
    verdict: Optional[str] = Query(None, description="Filter: scam, genuine, unsure"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    store: InMemoryCallStore = Depends(get_dashboard_store),
):
    all_calls = store.get_calls(verdict=verdict, limit=1000)
    start_idx = (page - 1) * limit
    return all_calls[start_idx : start_idx + limit]


@router.get("/dashboard/api/calls/{call_id}", response_model=Dict[str, Any])
def get_call_api(
    call_id: str,
    auth_token: str = Depends(verify_dashboard_auth),
    store: InMemoryCallStore = Depends(get_dashboard_store),
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
    auth_token: str = Depends(verify_dashboard_auth),
    store: InMemoryCallStore = Depends(get_dashboard_store),
):
    record = store.get_call(call_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call record '{call_id}' not found",
        )

    caller = record.get("caller_number") or "Not captured"
    intel = record.get("extracted_intel", {}) or {}
    upi_str = ", ".join(intel.get("upi_ids", [])) or "Not captured"
    acc_str = ", ".join(intel.get("bank_accounts", [])) or "Not captured"
    ifsc_str = ", ".join(intel.get("ifsc_codes", [])) or "Not captured"
    ph_str = ", ".join(intel.get("phone_numbers", [])) or "Not captured"
    summary = record.get("summary") or "Not captured"
    duration = _safe_duration(record.get("duration"))

    created_raw = record.get("created_at") or record.get("timestamp")
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

NARRATIVE SUMMARY:
{summary}

VERIFICATION NOTE FOR FAMILY:
Please review and verify the above captured evidence with the elder before
formal submission to the National Cybercrime Reporting Portal (1930).
================================================================================
Generated by GuardianLine Autonomous Protection System
"""
    return Response(
        content=report_text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"inline; filename=1930_report_{call_id}.txt"},
    )
