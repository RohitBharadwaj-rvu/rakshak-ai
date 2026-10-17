"""
FastAPI Router for GuardianLine Family Dashboard (Lane C / T-DASH).
Serves mobile-responsive UI (360px+ compatible) and secure JSON APIs.
"""

import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse

from app.dashboard.store import InMemoryCallStore, get_dashboard_store

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DEFAULT_DASHBOARD_TOKEN = "local_dash_token_secret"


def verify_dashboard_auth(
    token: Optional[str] = Query(None, description="Dashboard auth token query parameter"),
    authorization: Optional[str] = Header(None, description="Bearer token authentication header"),
) -> str:
    expected_token = os.environ.get("GUARDIAN_DASHBOARD_TOKEN", DEFAULT_DASHBOARD_TOKEN)

    candidate_token = None
    if authorization and authorization.lower().startswith("bearer "):
        candidate_token = authorization[7:].strip()
    elif token:
        candidate_token = token.strip()

    if not candidate_token or candidate_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid or missing dashboard token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return candidate_token


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def render_dashboard(
    auth_token: str = Depends(verify_dashboard_auth),
    verdict: Optional[str] = Query(None),
    store: InMemoryCallStore = Depends(get_dashboard_store),
):
    calls = store.get_calls(verdict=verdict, limit=50)

    # Generate HTML Cards
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
            c_id = c.get("call_id", "")
            caller = c.get("caller_number", "Unknown")
            v = str(c.get("verdict", "unsure")).lower()
            duration = c.get("duration", 0)
            summary = c.get("summary", "No summary available")
            intel = c.get("extracted_intel", {}) or {}

            badge_class = "badge-scam" if v == "scam" else ("badge-genuine" if v == "genuine" else "badge-unsure")
            badge_text = "🚨 SCAM BLOCKED" if v == "scam" else ("✅ GENUINE" if v == "genuine" else "❓ UNSURE")

            intel_items = []
            for upi in intel.get("upi_ids", []):
                intel_items.append(f'<span class="intel-tag upi">UPI: {upi}</span>')
            for acc in intel.get("bank_accounts", []):
                intel_items.append(f'<span class="intel-tag acc">A/C: {acc}</span>')
            for ph in intel.get("phone_numbers", []):
                intel_items.append(f'<span class="intel-tag ph">Ph: {ph}</span>')
            intel_html = " ".join(intel_items) if intel_items else "<span class='text-muted'>No payment intel recorded</span>"

            card = f"""
            <div class="call-card {v}">
                <div class="card-header">
                    <span class="badge {badge_class}">{badge_text}</span>
                    <span class="duration">{duration:.0f}s</span>
                </div>
                <div class="caller-number">{caller}</div>
                <div class="summary">{summary}</div>
                <div class="intel-box">{intel_html}</div>
                <div class="card-footer">
                    <span class="call-id">ID: {c_id}</span>
                    <a href="/dashboard/report/{c_id}?token={auth_token}" class="btn-dossier" target="_blank">1930 Dossier</a>
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
        .intel-tag.ph {{ background: #701a75; color: #f5d0fe; }}
        .text-muted {{ font-size: 12px; color: #64748b; font-style: italic; }}
        .card-footer {{ display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #334155; padding-top: 10px; }}
        .call-id {{ font-size: 11px; color: #64748b; font-family: monospace; }}
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

        /* Ensure 360px narrow phone viewports fit without sideways scrolling */
        @media (max-width: 360px) {{
            body {{ padding: 10px; }}
            h1 {{ font-size: 18px; }}
            .caller-number {{ font-size: 16px; }}
            .btn-dossier {{ padding: 4px 8px; font-size: 11px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🛡️ GuardianLine Shield</h1>
            <div class="subtitle">Autonomous Voice Screening & Honeypot Protection</div>
        </header>
        <main>
            {cards_html}
        </main>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@router.get("/api/calls", response_model=List[Dict[str, Any]])
def list_calls(
    auth_token: str = Depends(verify_dashboard_auth),
    verdict: Optional[str] = Query(None, description="Filter by verdict: scam, genuine, unsure"),
    limit: int = Query(50, ge=1, le=100),
    store: InMemoryCallStore = Depends(get_dashboard_store),
):
    return store.get_calls(verdict=verdict, limit=limit)


@router.get("/api/calls/{call_id}", response_model=Dict[str, Any])
def get_call_detail(
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


@router.get("/report/{call_id}")
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

    caller = record.get("caller_number", "Not captured")
    intel = record.get("extracted_intel", {}) or {}
    upi_str = ", ".join(intel.get("upi_ids", [])) or "Not captured"
    acc_str = ", ".join(intel.get("bank_accounts", [])) or "Not captured"
    ph_str = ", ".join(intel.get("phone_numbers", [])) or "Not captured"
    summary = record.get("summary", "Suspected telecom financial fraud.")

    report_text = f"""================================================================================
NATIONAL CYBERCRIME REPORTING PORTAL (1930 / cybercrime.gov.in)
PRE-FILLED INCIDENT DOSSIER
================================================================================
INCIDENT DETAILS:
- Case Reference ID: {call_id}
- Suspect Telephony Number: {caller}
- Attack Category: Telecom Impersonation / Voice Phishing (Vishing)
- Suspect UPI Handles: {upi_str}
- Suspect Bank Account(s): {acc_str}
- Associated Callbacks: {ph_str}

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
