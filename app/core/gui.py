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
import json
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
from app.voice.evidence import build_chakshu_packet, build_report_suspect_packets


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
        dependent_id: Optional[str] = None,
        dependent_ids: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Returns (paged_calls, total_matching_count)."""
        pass

    @abstractmethod
    def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        pass

    def confirm_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        record = self.get_call(call_id)
        if not record:
            return None
        record["evidence_status"] = "confirmed_by_family"
        record["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        return record

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
        dependent_id: Optional[str] = None,
        dependent_ids: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            calls = list(self._calls.values())

        # Sort chronologically (newest first)
        calls.sort(key=_parse_timestamp, reverse=True)

        if verdict:
            v_lower = verdict.lower()
            calls = [c for c in calls if str(c.get("verdict", "")).lower() == v_lower]

        if dependent_id:
            calls = [c for c in calls if str(c.get("dependent_id", "")) == dependent_id]
        elif dependent_ids is not None:
            allowed = set(dependent_ids)
            calls = [c for c in calls if str(c.get("dependent_id", "")) in allowed]

        total_count = len(calls)
        start_idx = max(0, (page - 1) * limit)
        end_idx = start_idx + limit
        return calls[start_idx:end_idx], total_count

    def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._calls.get(call_id)

    def confirm_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._calls.get(call_id)
            if not rec:
                return None
            rec["evidence_status"] = "confirmed_by_family"
            rec["confirmed_at"] = datetime.now(timezone.utc).isoformat()
            return dict(rec)

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


def _extract_call_upi_and_accounts(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Extract normalized (kind, identifier) pairs for 'upi' and 'account' from a CallRecord.
    """
    intel = record.get("extracted_intel") or {}
    if not isinstance(intel, dict):
        intel = {}

    found: List[Tuple[str, str]] = []
    seen = set()

    for upi in intel.get("upi_ids") or []:
        val = str(upi).strip().lower()
        if val and ("upi", val) not in seen:
            seen.add(("upi", val))
            found.append(("upi", val))

    for field in ("bank_accounts", "account_numbers"):
        for acc in intel.get(field) or []:
            val = str(acc).strip()
            if val and ("account", val) not in seen:
                seen.add(("account", val))
                found.append(("account", val))

    for log_item in intel.get("mid_call_logs") or []:
        if not isinstance(log_item, dict):
            continue
        k = str(log_item.get("type") or log_item.get("kind") or "").strip().lower()
        raw_val = str(log_item.get("normalized_value") or log_item.get("value") or "").strip()
        if not raw_val:
            continue
        if k == "upi":
            val = raw_val.lower()
            if ("upi", val) not in seen:
                seen.add(("upi", val))
                found.append(("upi", val))
        elif k == "account":
            if ("account", raw_val) not in seen:
                seen.add(("account", raw_val))
                found.append(("account", raw_val))

    return found


def build_scam_intelligence(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates scam intelligence across CallRecords, linking calls that share the same
    UPI ID or bank account number.
    """
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for c in calls:
        call_id = str(c.get("call_id") or "").strip()
        if not call_id:
            continue
        for kind, ident in _extract_call_upi_and_accounts(c):
            key = (kind, ident)
            groups.setdefault(key, [])
            if not any(existing.get("call_id") == call_id for existing in groups[key]):
                groups[key].append(c)

    clusters: List[Dict[str, Any]] = []
    shared_by_call_id: Dict[str, List[Dict[str, Any]]] = {}

    for (kind, ident), matched_calls in groups.items():
        call_ids = [str(c.get("call_id")) for c in matched_calls]
        caller_numbers = []
        for c in matched_calls:
            num = str(c.get("caller_number") or "Unknown")
            if num not in caller_numbers:
                caller_numbers.append(num)

        call_summaries = [
            {
                "call_id": str(c.get("call_id") or ""),
                "caller_number": str(c.get("caller_number") or "Unknown"),
                "verdict": str(c.get("verdict") or "unsure"),
                "duration": _safe_duration(c.get("duration")),
                "summary": str(c.get("summary") or ""),
                "start_time": str(c.get("start_time") or c.get("created_at") or ""),
            }
            for c in matched_calls
        ]
        cluster = {
            "kind": kind,
            "identifier": ident,
            "call_count": len(matched_calls),
            "linked_across_calls": len(matched_calls) >= 2,
            "call_ids": call_ids,
            "caller_numbers": caller_numbers,
            "calls": call_summaries,
        }
        clusters.append(cluster)

        if len(matched_calls) >= 2:
            for cid in call_ids:
                peers = [s for s in call_summaries if s["call_id"] != cid]
                shared_by_call_id.setdefault(cid, []).append(
                    {
                        "kind": kind,
                        "identifier": ident,
                        "peer_calls": peers,
                    }
                )

    clusters.sort(key=lambda item: (-item["call_count"], item["kind"], item["identifier"]))
    linked_clusters = [c for c in clusters if c["linked_across_calls"]]
    return {
        "total_identifiers": len(clusters),
        "linked_cluster_count": len(linked_clusters),
        "clusters": clusters,
        "linked_clusters": linked_clusters,
        "shared_by_call_id": shared_by_call_id,
    }



def _resolve_dependent_filter(
    dependent_id: Optional[str] = None,
    caretaker_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[List[str]]]:
    """
    Resolves query filters `(dependent_id, dependent_ids)`:
    - If `dependent_id` is specified, filters to that single dependent.
    - Else if `caretaker_id` is specified, resolves all dependents monitored by that caretaker.
    """
    if dependent_id:
        return dependent_id, None
    if caretaker_id:
        from app.core.family import get_family_registry
        deps = get_family_registry().get_dependents_for_caretaker(caretaker_id)
        return None, [str(d["dependent_id"]) for d in deps]
    return None, None


@router.get("/dashboard", response_class=HTMLResponse)
@router.get("/dashboard/", response_class=HTMLResponse)
@router.get("/gui", response_class=HTMLResponse)
@router.get("/gui/", response_class=HTMLResponse)
def render_dashboard(
    request: Request,
    auth_token: str = Depends(verify_overview_auth),
    token: Optional[str] = Query(None),
    verdict: Optional[str] = Query(None, pattern="^(scam|genuine|unsure)$"),
    dependent_id: Optional[str] = Query(None),
    caretaker_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    if token:
        return _session_redirect(request, auth_token)

    dep_single, dep_list = _resolve_dependent_filter(dependent_id=dependent_id, caretaker_id=caretaker_id)
    calls, total_calls = store.get_calls(
        verdict=verdict,
        page=page,
        limit=limit,
        dependent_id=dep_single,
        dependent_ids=dep_list,
    )
    all_calls, _ = store.get_calls(
        verdict=None,
        page=1,
        limit=500,
        dependent_id=dep_single,
        dependent_ids=dep_list,
    )
    scam_intel = build_scam_intelligence(all_calls)

    # Check for active pending scam calls for real-time honeypot banner
    pending_scam_calls = [
        c for c in calls
        if str(c.get("status") or "").lower() == "pending" and str(c.get("verdict") or "").lower() == "scam"
    ]
    live_banner_html = ""
    if pending_scam_calls:
        banner_items = []
        for pc in pending_scam_calls:
            pcid = str(pc.get("call_id") or "")
            pcid_esc = html.escape(pcid)
            pc_path = html.escape(quote(pcid, safe=""))
            persona = html.escape(str(pc.get("persona_name") or "Ramesh Sharma"))
            intel = pc.get("extracted_intel", {}) or {}
            mid_logs = intel.get("mid_call_logs", []) or pc.get("mid_call_logs", [])

            live_tags = []
            for u in intel.get("upi_ids", []):
                live_tags.append(f'<span class="intel-tag upi">UPI: {html.escape(str(u))}</span>')
            for a in intel.get("bank_accounts", []):
                live_tags.append(f'<span class="intel-tag acc">A/C: {html.escape(str(a))}</span>')
            for i in intel.get("ifsc_codes", []):
                live_tags.append(f'<span class="intel-tag ifsc">IFSC: {html.escape(str(i))}</span>')
            for ph in intel.get("phone_numbers", []):
                live_tags.append(f'<span class="intel-tag ph">Ph: {html.escape(str(ph))}</span>')
            for m in mid_logs:
                if isinstance(m, dict):
                    m_val = str(m.get("normalized_value") or m.get("value_as_heard") or m.get("value") or "")
                    m_type = str(m.get("type") or m.get("kind") or "intel").upper()
                    if m_val and not any(m_val in t for t in live_tags):
                        live_tags.append(f'<span class="intel-tag upi">{html.escape(m_type)}: {html.escape(m_val)}</span>')

            tags_html = " ".join(live_tags) if live_tags else "<span class='text-muted'>Active stall in progress · awaiting payment or credential disclosure...</span>"

            banner_items.append(
                f'''
                <div class="live-call-item">
                    <div class="live-call-meta">
                        <div><strong>Active Call ID:</strong> <a href="/dashboard/calls/{pc_path}" class="live-call-link">{pcid_esc}</a></div>
                        <div><strong>Persona:</strong> {persona}</div>
                    </div>
                    <div class="intel-box" style="margin-bottom: 8px;">{tags_html}</div>
                    <div><a href="/dashboard/calls/{pc_path}" class="btn-detail" style="display: inline-block;">Inspect Live Honeypot →</a></div>
                </div>
                '''
            )

        live_banner_html = f'''
        <div id="live-honeypot-banner" class="live-banner">
            <div class="live-banner-header">
                <span class="live-pulse-dot">🔴</span>
                <strong>LIVE HONEYPOT ACTIVE — Ramesh AI is stalling a suspected scammer right now</strong>
            </div>
            {"".join(banner_items)}
        </div>
        '''

    linked_clusters = scam_intel["linked_clusters"]

    if linked_clusters:
        intel_rows = []
        for cl in linked_clusters[:10]:
            k_label = "UPI" if cl["kind"] == "upi" else "Bank A/C"
            ident_esc = html.escape(cl["identifier"])
            links_html = " · ".join(
                f'<a href="/dashboard/calls/{html.escape(quote(cid, safe=""))}" class="intel-call-link">{html.escape(cid)}</a>'
                for cid in cl["call_ids"]
            )
            intel_rows.append(
                f'<div class="linked-intel-row">'
                f'<span class="intel-tag {"upi" if cl["kind"] == "upi" else "acc"}">{k_label}: {ident_esc}</span> '
                f'<span class="linked-count">Shared across {cl["call_count"]} calls:</span> {links_html}'
                f'</div>'
            )
        intel_banner_html = f"""
        <div class="intel-summary-card">
            <div class="card-header">
                <strong>🔗 Scam Intelligence · Linked UPI IDs &amp; Bank Accounts ({len(linked_clusters)})</strong>
                <a href="/dashboard/intelligence" class="btn-detail">Open Scam Intelligence View →</a>
            </div>
            {"".join(intel_rows)}
        </div>
        """
    else:
        intel_banner_html = """
        <div class="intel-summary-card">
            <div class="card-header">
                <strong>🔗 Scam Intelligence · Cross-Call UPI &amp; Account Linker</strong>
                <a href="/dashboard/intelligence" class="btn-detail">Open Scam Intelligence View →</a>
            </div>
            <div class="text-muted">Links calls sharing the same attacker UPI ID or bank account across incidents.</div>
        </div>
        """

    from app.core.family import get_family_registry
    family_topology = get_family_registry().get_family_topology()
    caretakers_topo = family_topology.get("caretakers", [])
    dependents_topo = family_topology.get("dependents", [])
    family_filter_html = ""
    if caretakers_topo or dependents_topo:
        ct_pills = [
            f'<a href="/dashboard" class="btn-detail" style="border: 1px solid {"#38bdf8" if not caretaker_id and not dependent_id else "#334155"};">👨‍👩‍👧‍👦 All Family</a>'
        ]
        for ct in caretakers_topo:
            cid = html.escape(quote(str(ct["caretaker_id"]), safe=""))
            cname = html.escape(str(ct["name"]))
            crole = html.escape(str(ct.get("role", "parent")).title())
            active_border = "#38bdf8" if caretaker_id == ct["caretaker_id"] else "#334155"
            ct_pills.append(
                f'<a href="/dashboard?caretaker_id={cid}" class="btn-detail" style="border: 1px solid {active_border};">👁️ {cname} ({crole})</a>'
            )
        dep_pills = []
        for dp in dependents_topo:
            did = html.escape(quote(str(dp["dependent_id"]), safe=""))
            dname = html.escape(str(dp["name"]))
            drole = html.escape(str(dp.get("role", "grandparent")).title())
            active_border = "#22c55e" if dependent_id == dp["dependent_id"] else "#334155"
            dep_pills.append(
                f'<a href="/dashboard?dependent_id={did}" class="btn-detail" style="border: 1px solid {active_border};">🛡️ {dname} ({drole})</a>'
            )
        family_filter_html = f"""
        <div class="intel-summary-card" style="border-left-color: #22c55e;">
            <div class="card-header" style="margin-bottom: 8px;">
                <strong>👨‍👩‍👧‍👦 Family Protection Circle · Multi-Caretaker &amp; Dependent Filter</strong>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px;">{"".join(ct_pills)}</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">{"".join(dep_pills)}</div>
        </div>
        """


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
            if v not in ("scam", "genuine", "unsure", "safe_delivery", "legitimate_verified"):
                v = "unsure"

            duration_num = _safe_duration(c.get("duration"))
            summary = html.escape(str(c.get("summary") or "No summary recorded."))
            intel = c.get("extracted_intel", {}) or {}

            if v == "scam":
                badge_class = "badge-scam"
                badge_text = "🚨 SUSPECTED SCAM"
            elif v in ("genuine", "safe_delivery", "legitimate_verified"):
                badge_class = "badge-genuine"
                badge_text = "✅ VERIFIED DELIVERY" if "delivery" in v else "✅ GENUINE"
            else:
                badge_class = "badge-unsure"
                badge_text = "❓ UNSURE"

            fam_status = str(c.get("family_verification_status") or "NONE").upper()
            fam_badge = ""
            if fam_status == "CONFIRMED_SAFE":
                fam_badge = '<div style="margin-bottom:8px;"><span class="badge" style="background:#14532d;color:#86efac;font-size:11px;">✅ AMIT CONFIRMED SAFE IN PUNE</span></div>'
            elif fam_status == "PENDING":
                fam_badge = f'<div style="margin-bottom:8px;"><span class="badge" style="background:#78350f;color:#fde68a;font-size:11px;">⏳ VERIFYING AMIT SAFE...</span> <button onclick="confirmSafe(\'{c_id}\')" style="background:#2563eb;color:white;border:none;border-radius:4px;padding:3px 8px;font-size:11px;cursor:pointer;margin-left:6px;">Simulate Amit SAFE Reply</button></div>'

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

            dep_name_raw = str(c.get("dependent_name") or "").strip()
            dep_role_raw = str(c.get("dependent_role") or "").strip()
            dep_badge_html = ""
            if dep_name_raw:
                role_suffix = f" ({html.escape(dep_role_raw.title())})" if dep_role_raw else ""
                dep_badge_html = f'<div style="margin-bottom: 6px;"><span class="intel-tag ifsc">🛡️ Protected: {html.escape(dep_name_raw)}{role_suffix}</span></div>'

            card = f"""
            <div class="call-card {v}">
                <div class="card-header">
                    <span class="badge {badge_class}">{badge_text}</span>
                    <span class="duration">{duration_num:.0f}s</span>
                </div>
                {fam_badge}
                {dep_badge_html}
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
        #live-honeypot-banner {{
            background: #1e1b4b;
            border: 2px solid #ef4444;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 20px;
            box-shadow: 0 0 15px rgba(239, 68, 68, 0.4);
            animation: livePulse 2s infinite;
        }}
        @keyframes livePulse {{
            0% {{ box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.6); }}
            70% {{ box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }}
        }}
        .live-banner-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 15px;
            font-weight: 700;
            color: #fca5a5;
            margin-bottom: 10px;
        }}
        .live-call-item {{
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 12px;
            margin-top: 8px;
        }}
        .live-call-meta {{
            font-size: 13px;
            color: #cbd5e1;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .live-call-link {{
            color: #38bdf8;
            text-decoration: none;
            font-weight: 600;
            font-family: monospace;
            font-size: 13px;
        }}
        .live-call-link:hover {{
            text-decoration: underline;
        }}
        .intel-summary-card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-left: 4px solid #38bdf8;
            border-radius: 12px;
            padding: 14px 16px;
            margin-bottom: 16px;
        }}
        .linked-intel-row {{
            font-size: 13px;
            margin-top: 8px;
            color: #cbd5e1;
        }}
        .linked-count {{ color: #fca5a5; font-weight: 600; margin-left: 6px; }}
        .intel-call-link {{ color: #38bdf8; text-decoration: none; font-family: monospace; font-size: 12px; }}
        .nav-links {{ margin-top: 10px; display: flex; gap: 12px; }}
        .nav-links a {{ color: #38bdf8; text-decoration: none; font-size: 13px; font-weight: 600; }}


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
            <div class="nav-links">
                <a href="/dashboard">Calls Overview</a>
                <a href="/dashboard/intelligence">🔗 Scam Intelligence (Shared UPI / Accounts)</a>
            </div>
        </header>
        <main>
            {live_banner_html}
            {family_filter_html}
            {intel_banner_html}
            {cards_html}
            {pagination_html}
        </main>

    </div>
    <script>
        (function() {{
            window.confirmSafe = function(callId) {{
                fetch('/api/calls/' + encodeURIComponent(callId) + '/verify_son_safe', {{method: 'POST'}})
                    .then(function(r) {{ return r.json(); }})
                    .then(function(d) {{ window.location.reload(); }})
                    .catch(function(err) {{ console.error("Verify safe error:", err); }});
            }};

            if (window.EventSource) {{
                var es = new EventSource('/dashboard/sse');
                es.addEventListener('family_verification_pending', function(e) {{ window.location.reload(); }});
                es.addEventListener('family_verified_safe', function(e) {{ window.location.reload(); }});
                es.addEventListener('legitimate_caller_approved', function(e) {{ window.location.reload(); }});
                es.addEventListener('syndicate_match_detected', function(e) {{ window.location.reload(); }});
            }}

            var params = new URLSearchParams(window.location.search);
            var isLive = params.get("live") === "1";
            var hasPending = Boolean(document.getElementById("live-honeypot-banner") || document.body.innerHTML.includes('"status": "pending"') || document.body.innerHTML.includes('status="pending"'));
            if (isLive || hasPending) {{
                setTimeout(function() {{
                    window.location.reload();
                }}, 4000);
            }}
        }})();
    </script>
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

    is_pending_js = "true" if str(record.get("status") or "").lower() == "pending" else "false"
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

    # Build Evidence Section (Chakshu Packet + Report Suspect Packets + Review & Confirm)
    chakshu = build_chakshu_packet(record)
    suspect_packets = build_report_suspect_packets(record)
    chakshu_dict = chakshu.model_dump() if hasattr(chakshu, "model_dump") else chakshu.dict()
    chakshu_json_escaped = html.escape(json.dumps(chakshu_dict, indent=2, ensure_ascii=False))
    chakshu_summary_escaped = html.escape(chakshu.evidence_summary)
    chakshu_category_escaped = html.escape(chakshu.category)
    ev_hash_escaped = html.escape(chakshu.evidence_hash_sha256)

    ev_status = str(record.get("evidence_status") or "draft")
    confirmed_at = html.escape(str(record.get("confirmed_at") or ""))
    safe_call_path = html.escape(quote(call_id, safe=""))
    escaped_auth = html.escape(auth)

    if ev_status == "confirmed_by_family":
        status_badge_html = (
            f'<div class="ev-status confirmed">✅ Confirmed by Family'
            f'{f" · {confirmed_at}" if confirmed_at else ""} (Manual portal submission only · never auto-submitted)</div>'
        )
    else:
        status_badge_html = (
            '<div class="ev-status draft">⏳ Draft · Pending Family Review &amp; Confirmation '
            '(Nothing is auto-submitted to any portal)</div>'
        )

    suspect_cards_html_list = []
    for idx, pkt in enumerate(suspect_packets):
        pkt_dict = pkt.to_dict()
        pkt_json_esc = html.escape(json.dumps(pkt_dict, indent=2, ensure_ascii=False))
        kind_esc = html.escape(pkt.kind.upper())
        val_norm_esc = html.escape(pkt.value_normalized)
        val_raw_esc = html.escape(pkt.value_raw)
        quote_line = f'<div class="pkt-meta">Quote: "{html.escape(pkt.quote)}"</div>' if pkt.quote else ""
        elicit_line = f'<div class="pkt-meta">Tactic: {html.escape(pkt.elicitation)}</div>' if pkt.elicitation else ""
        suspect_cards_html_list.append(
            f"""
            <div class="packet-item">
                <div class="packet-row">
                    <span class="intel-tag upi">{kind_esc}: {val_norm_esc}</span>
                    <div class="copy-group">
                        <button type="button" class="btn-copy" data-copy-text="{val_norm_esc}" onclick="copyBtnText(this)">Copy {kind_esc}</button>
                        <button type="button" class="btn-copy" data-copy-target="suspect-pkt-{idx}" onclick="copyFromTarget(this)">Copy Packet</button>
                    </div>
                </div>
                <div class="pkt-meta">Spoken / Raw: {val_raw_esc} · Status: {html.escape(pkt.status)}</div>
                {quote_line}
                {elicit_line}
                <pre id="suspect-pkt-{idx}" class="packet-pre">{pkt_json_esc}</pre>
            </div>
            """
        )
    suspect_packets_html = (
        "\n".join(suspect_cards_html_list)
        if suspect_cards_html_list
        else "<div class='text-muted'>No suspect identifiers captured in this call.</div>"
    )

    # Cross-linked calls sharing the same UPI ID or bank account (shown for overview-authorized sessions)
    linked_calls_card_html = ""
    if not auth:
        all_calls, _ = store.get_calls(verdict=None, page=1, limit=500)
        scam_intel = build_scam_intelligence(all_calls)
        shared_links = scam_intel["shared_by_call_id"].get(call_id, [])
        if shared_links:
            shared_items_html = []
            for item in shared_links:
                k_label = "UPI ID" if item["kind"] == "upi" else "Bank Account"
                ident_esc = html.escape(item["identifier"])
                peer_links = ", ".join(
                    f'<a href="/dashboard/calls/{html.escape(quote(p["call_id"], safe=""))}" style="color: #38bdf8; font-family: monospace;">{html.escape(p["call_id"])} ({html.escape(p["caller_number"])})</a>'
                    for p in item["peer_calls"]
                )
                shared_items_html.append(
                    f'<div class="pkt-meta" style="margin-bottom: 6px; color: #e2e8f0;">'
                    f'<strong>Shared {k_label} <code>{ident_esc}</code>:</strong> also seen in {peer_links}'
                    f'</div>'
                )
            linked_calls_card_html = f"""
            <div class="card" id="linked-scam-intelligence">
                <h2>🔗 Scam Intelligence · Linked Calls Sharing Same UPI / Account</h2>
                {"".join(shared_items_html)}
                <div style="margin-top: 8px;"><a href="/dashboard/intelligence" style="color: #38bdf8; font-size: 13px;">View full Scam Intelligence graph →</a></div>
            </div>
            """


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
        .container {{ max-width: 640px; margin: 0 auto; }}
        .back-link {{ display: inline-block; color: #38bdf8; text-decoration: none; margin-bottom: 16px; font-size: 14px; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
        h2 {{ font-size: 18px; margin-bottom: 12px; color: #e2e8f0; }}
        h3 {{ font-size: 15px; margin-top: 14px; margin-bottom: 8px; color: #38bdf8; }}
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
        .btn-portal {{
            display: inline-block;
            background: #0f766e;
            color: #f0fdfa;
            text-decoration: none;
            padding: 8px 12px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 13px;
            margin-right: 8px;
            margin-bottom: 8px;
        }}
        .btn-confirm {{
            background: #16a34a;
            color: #ffffff;
            border: none;
            padding: 10px 16px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 14px;
            cursor: pointer;
        }}
        .btn-copy {{
            background: #334155;
            color: #e2e8f0;
            border: 1px solid #475569;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            cursor: pointer;
        }}
        .copy-group {{ display: flex; gap: 6px; flex-wrap: wrap; }}
        .packet-item {{
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
        }}
        .packet-row {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }}
        .pkt-meta {{ font-size: 12px; color: #94a3b8; margin-bottom: 4px; }}
        .packet-pre {{
            font-family: monospace;
            font-size: 11px;
            color: #cbd5e1;
            white-space: pre-wrap;
            word-break: break-all;
            background: #1e293b;
            padding: 8px;
            border-radius: 6px;
            margin-top: 6px;
        }}
        .ev-status {{ padding: 10px 12px; border-radius: 8px; font-size: 13px; font-weight: 600; margin-bottom: 12px; }}
        .ev-status.draft {{ background: #422006; color: #fde68a; border: 1px solid #854d0e; }}
        .ev-status.confirmed {{ background: #052e16; color: #86efac; border: 1px solid #166534; }}
        .confirm-form {{ margin-top: 12px; margin-bottom: 12px; padding: 12px; background: #0f172a; border-radius: 8px; border: 1px solid #334155; }}
    </style>
    <script>
        function copyFromTarget(btn) {{
            var targetId = btn.getAttribute("data-copy-target");
            var el = document.getElementById(targetId);
            if (!el) return;
            var text = el.innerText || el.textContent;
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(text);
            }}
            var orig = btn.innerText;
            btn.innerText = "Copied!";
            setTimeout(function() {{ btn.innerText = orig; }}, 1500);
        }}
        function copyBtnText(btn) {{
            var text = btn.getAttribute("data-copy-text") || "";
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(text);
            }}
            var orig = btn.innerText;
            btn.innerText = "Copied!";
            setTimeout(function() {{ btn.innerText = orig; }}, 1500);
        }}
    </script>
</head>
<body>
    <div class="container">
        {back_link}
        <div class="card">
            <div><span class="badge {badge_class}">{badge_text}</span></div>
            <div class="caller">{caller}</div>
            <div class="summary">{summary}</div>
            <div class="intel-box">{intel_html}</div>
            <a href="/dashboard/report/{safe_call_path}{escaped_auth}" class="btn-dossier" target="_blank">Download draft 1930 report</a>
        </div>
        <div class="card" id="evidence-section">
            <h2>Evidence &amp; Citizen Reporting Packets</h2>
            {status_badge_html}
            <form method="post" action="/dashboard/calls/{safe_call_path}/confirm{escaped_auth}" class="confirm-form">
                <p class="pkt-meta" style="margin-bottom: 8px;">
                    Step 1: Review captured details with your parent. Step 2: Confirm below. Step 3: Copy a packet and file manually on Chakshu or cybercrime.gov.in.
                </p>
                <button type="submit" class="btn-confirm">Review and Confirm Evidence</button>
            </form>
            <div style="margin-bottom: 12px;">
                <a href="https://sancharsaathi.gov.in/sfc/" class="btn-portal" target="_blank" rel="noopener noreferrer">Report on Chakshu (sancharsaathi.gov.in) ↗</a>
                <a href="https://cybercrime.gov.in" class="btn-portal" target="_blank" rel="noopener noreferrer">National Cybercrime Portal (cybercrime.gov.in) ↗</a>
            </div>
            <h3>1. DoT Sanchar Saathi (Chakshu) Packet</h3>
            <div class="packet-item">
                <div class="packet-row">
                    <strong>Category: {chakshu_category_escaped}</strong>
                    <div class="copy-group">
                        <button type="button" class="btn-copy" data-copy-target="chakshu-summary" onclick="copyFromTarget(this)">Copy Chakshu Summary</button>
                        <button type="button" class="btn-copy" data-copy-target="chakshu-json" onclick="copyFromTarget(this)">Copy Chakshu Packet</button>
                    </div>
                </div>
                <div class="pkt-meta">Integrity SHA-256: <code>{ev_hash_escaped}</code></div>
                <pre id="chakshu-summary" class="packet-pre">{chakshu_summary_escaped}</pre>
                <pre id="chakshu-json" class="packet-pre">{chakshu_json_escaped}</pre>
            </div>
            <h3>2. Report Suspect Packets ({len(suspect_packets)})</h3>
            {suspect_packets_html}
        </div>
        {linked_calls_card_html}
        <div class="card">
            <h2>Call Transcript ({duration:.0f}s)</h2>

            {transcript_content}
        </div>
    </div>
    <script>
        (function() {{
            var params = new URLSearchParams(window.location.search);
            var isLive = params.get("live") === "1";
            var isPending = {is_pending_js};
            if (isLive || isPending) {{
                setTimeout(function() {{
                    window.location.reload();
                }}, 4000);
            }}
        }})();
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)



@router.post("/dashboard/calls/{call_id}/confirm")
def confirm_call_evidence_ui(
    request: Request,
    call_id: str,
    auth: str = Depends(verify_call_access),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    record = store.confirm_call(call_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call record '{call_id}' not found",
        )
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return {
            "call_id": call_id,
            "evidence_status": record.get("evidence_status", "confirmed_by_family"),
            "confirmed_at": record.get("confirmed_at"),
            "auto_submitted": False,
            "portal_submission": "manual_only",
        }
    safe_path = quote(call_id, safe="")
    return RedirectResponse(
        url=f"/dashboard/calls/{safe_path}{auth}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/dashboard/api/intelligence", response_model=Dict[str, Any])
def get_scam_intelligence_api(
    auth_token: str = Depends(verify_overview_auth),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    calls, _ = store.get_calls(verdict=None, page=1, limit=500)
    return build_scam_intelligence(calls)


@router.get("/dashboard/intelligence", response_class=HTMLResponse)
@router.get("/gui/intelligence", response_class=HTMLResponse)
def render_scam_intelligence_view(
    request: Request,
    auth_token: str = Depends(verify_overview_auth),
    token: Optional[str] = Query(None),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    if token:
        return _session_redirect(request, auth_token)

    calls, _ = store.get_calls(verdict=None, page=1, limit=500)
    intel_report = build_scam_intelligence(calls)
    clusters = intel_report["clusters"]

    if not clusters:
        clusters_html = """
        <div class="card">
            <div class="text-muted">No UPI IDs or bank accounts extracted yet.</div>
        </div>
        """
    else:
        cluster_cards = []
        for cl in clusters:
            kind_label = "UPI ID" if cl["kind"] == "upi" else "Bank Account"
            ident_esc = html.escape(cl["identifier"])
            badge = (
                f'<span class="badge badge-scam">🔗 LINKED ACROSS {cl["call_count"]} CALLS</span>'
                if cl["linked_across_calls"]
                else '<span class="badge badge-unsure">1 CALL</span>'
            )
            call_rows = []
            for c_item in cl["calls"]:
                cid_esc = html.escape(c_item["call_id"])
                cid_path = html.escape(quote(c_item["call_id"], safe=""))
                cnum_esc = html.escape(c_item["caller_number"])
                csum_esc = html.escape(c_item["summary"] or "No summary")
                call_rows.append(
                    f'<div class="call-row">'
                    f'<a href="/dashboard/calls/{cid_path}" class="call-link">{cid_esc}</a> · '
                    f'<strong>{cnum_esc}</strong> · <span class="summary-inline">{csum_esc}</span>'
                    f'</div>'
                )
            cluster_cards.append(
                f"""
                <div class="card">
                    <div class="cluster-header">
                        <div>
                            <span class="intel-tag {"upi" if cl["kind"] == "upi" else "acc"}">{kind_label}: {ident_esc}</span>
                        </div>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            {badge}
                            <button type="button" class="btn-copy" data-copy-text="{ident_esc}" onclick="copyBtnText(this)">Copy {kind_label}</button>
                        </div>
                    </div>
                    <div class="call-list">
                        {"".join(call_rows)}
                    </div>
                </div>
                """
            )
        clusters_html = "\n".join(cluster_cards)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scam Intelligence · GuardianLine</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            padding: 16px;
        }}
        .container {{ max-width: 640px; margin: 0 auto; }}
        .back-link {{ display: inline-block; color: #38bdf8; text-decoration: none; margin-bottom: 16px; font-size: 14px; }}
        header {{ margin-bottom: 20px; border-bottom: 1px solid #1e293b; padding-bottom: 14px; }}
        h1 {{ font-size: 20px; color: #38bdf8; }}
        .subtitle {{ font-size: 13px; color: #94a3b8; margin-top: 4px; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 14px; border: 1px solid #334155; }}
        .cluster-header {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
        .intel-tag {{ font-size: 13px; padding: 4px 10px; border-radius: 6px; font-family: monospace; font-weight: 700; }}
        .intel-tag.upi {{ background: #312e81; color: #c7d2fe; }}
        .intel-tag.acc {{ background: #064e3b; color: #a7f3d0; }}
        .badge {{ font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; }}
        .badge-scam {{ background: #7f1d1d; color: #fca5a5; }}
        .badge-unsure {{ background: #374151; color: #d1d5db; }}
        .btn-copy {{
            background: #334155;
            color: #e2e8f0;
            border: 1px solid #475569;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            cursor: pointer;
        }}
        .call-row {{ padding: 8px 0; border-top: 1px solid #334155; font-size: 13px; color: #e2e8f0; }}
        .call-link {{ color: #38bdf8; font-family: monospace; text-decoration: none; font-weight: 600; }}
        .summary-inline {{ color: #94a3b8; }}
        .text-muted {{ color: #64748b; font-size: 13px; }}
    </style>
    <script>
        function copyBtnText(btn) {{
            var text = btn.getAttribute("data-copy-text") || "";
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(text);
            }}
            var orig = btn.innerText;
            btn.innerText = "Copied!";
            setTimeout(function() {{ btn.innerText = orig; }}, 1500);
        }}
    </script>
</head>
<body>
    <div class="container">
        <a href="/dashboard" class="back-link">← Back to Overview</a>
        <header>
            <h1>🔗 Scam Intelligence View</h1>
            <div class="subtitle">Cross-call correlation linking scam calls that share the same UPI ID or bank account</div>
        </header>
        {clusters_html}
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@router.get("/dashboard/api/calls", response_model=List[Dict[str, Any]])
def list_calls_api(
    auth_token: str = Depends(verify_overview_auth),
    verdict: Optional[str] = Query(None, pattern="^(scam|genuine|unsure)$", description="Filter: scam, genuine, unsure"),
    dependent_id: Optional[str] = Query(None, description="Filter calls for a specific dependent"),
    caretaker_id: Optional[str] = Query(None, description="Filter calls across all dependents monitored by this caretaker"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    dep_single, dep_list = _resolve_dependent_filter(dependent_id=dependent_id, caretaker_id=caretaker_id)
    calls, _ = store.get_calls(
        verdict=verdict,
        page=page,
        limit=limit,
        dependent_id=dep_single,
        dependent_ids=dep_list,
    )
    return calls


@router.get("/dashboard/api/calls/{call_id}/dossier", response_model=Dict[str, Any])
def get_call_dossier_api(
    call_id: str,
    auth: str = Depends(verify_call_access),
    store: BaseCallStore = Depends(get_dashboard_store),
):
    """
    Consolidated mobile & web Caretaker Dossier endpoint returning:
    - Full CallRecord (with transcript, audio URL, dependent info, extracted intel)
    - Pre-formatted Chakshu packet & Report Suspect packets
    - Pre-filled 1930 Cybercrime report text
    - Cross-call shared scam intelligence links
    """
    record = store.get_call(call_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call record with ID '{call_id}' not found",
        )
    chakshu = build_chakshu_packet(record)
    chakshu_dict = chakshu.model_dump() if hasattr(chakshu, "model_dump") else chakshu.dict()
    suspect_packets = [pkt.to_dict() for pkt in build_report_suspect_packets(record)]

    if _REPORT_RENDERER is not None:
        report_1930_text = _REPORT_RENDERER(record)
    else:
        caller = record.get("caller_number") or "Not captured"
        summary = record.get("summary") or "Not captured"
        report_1930_text = f"1930 INCIDENT DOSSIER | Case: {call_id} | Suspect: {caller} | Summary: {summary}"

    all_calls, _ = store.get_calls(verdict=None, page=1, limit=500)
    scam_intel = build_scam_intelligence(all_calls)
    shared_links = scam_intel["shared_by_call_id"].get(call_id, [])

    return {
        "call": record,
        "evidence_status": record.get("evidence_status") or "draft",
        "confirmed_at": record.get("confirmed_at"),
        "chakshu_packet": chakshu_dict,
        "suspect_packets": suspect_packets,
        "report_1930_text": report_1930_text,
        "shared_scam_links": shared_links,
        "portals": {
            "chakshu_url": "https://sancharsaathi.gov.in/sfc/",
            "cybercrime_1930_url": "https://cybercrime.gov.in",
            "helpline_number": "1930",
        },
    }


@router.get("/dashboard/api/family", response_model=Dict[str, Any])
def get_family_topology_api(
    auth_token: str = Depends(verify_overview_auth),
    caretaker_id: Optional[str] = Query(None),
):
    from app.core.family import get_family_registry
    return get_family_registry().get_family_topology(caretaker_id=caretaker_id)


@router.post("/dashboard/api/family/dependents", response_model=Dict[str, Any])
async def register_dependent_api(
    request: Request,
    auth_token: str = Depends(verify_overview_auth),
):
    from app.core.family import get_family_registry
    body = await request.json()
    try:
        return get_family_registry().register_dependent(
            name=str(body.get("name") or ""),
            phone_number=str(body.get("phone_number") or ""),
            role=str(body.get("role") or "grandparent"),
            dependent_id=body.get("dependent_id"),
            device_status=str(body.get("device_status") or "active"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/dashboard/api/family/caretakers", response_model=Dict[str, Any])
async def register_caretaker_api(
    request: Request,
    auth_token: str = Depends(verify_overview_auth),
):
    from app.core.family import get_family_registry
    body = await request.json()
    try:
        return get_family_registry().register_caretaker(
            name=str(body.get("name") or ""),
            phone_number=str(body.get("phone_number") or ""),
            role=str(body.get("role") or "parent"),
            channel=str(body.get("channel") or "whatsapp"),
            caretaker_id=body.get("caretaker_id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/dashboard/api/family/links", response_model=Dict[str, Any])
async def link_caretakers_and_dependents_api(
    request: Request,
    auth_token: str = Depends(verify_overview_auth),
):
    from app.core.family import get_family_registry
    body = await request.json()
    reg = get_family_registry()
    label = str(body.get("relationship_label") or "")

    ct_ids = body.get("caretaker_ids") or ([body["caretaker_id"]] if body.get("caretaker_id") else [])
    dep_ids = body.get("dependent_ids") or ([body["dependent_id"]] if body.get("dependent_id") else [])
    if not ct_ids or not dep_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide caretaker_id(s) and dependent_id(s)",
        )
    created_links = []
    try:
        for cid in ct_ids:
            for did in dep_ids:
                created_links.append(
                    reg.link_caretaker_to_dependent(
                        caretaker_id=str(cid),
                        dependent_id=str(did),
                        relationship_label=label,
                    )
                )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"links": created_links}


@router.delete("/dashboard/api/family/links", response_model=Dict[str, Any])
def unlink_caretaker_and_dependent_api(
    caretaker_id: str = Query(...),
    dependent_id: str = Query(...),
    auth_token: str = Depends(verify_overview_auth),
):
    from app.core.family import get_family_registry
    removed = get_family_registry().unlink_caretaker_from_dependent(caretaker_id, dependent_id)
    return {"removed": removed, "caretaker_id": caretaker_id, "dependent_id": dependent_id}


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
