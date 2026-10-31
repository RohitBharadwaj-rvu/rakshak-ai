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

    from app.core import gui_theme as T
    from app.core.family import get_family_registry

    # Live honeypot banner for pending scam calls
    pending_scam_calls = [
        c for c in calls
        if str(c.get("status") or "").lower() == "pending" and str(c.get("verdict") or "").lower() == "scam"
    ]
    live_banner_html = ""
    if pending_scam_calls:
        live_items = []
        for pc in pending_scam_calls:
            pcid = str(pc.get("call_id") or "")
            pc_path = html.escape(quote(pcid, safe=""))
            persona = html.escape(str(pc.get("persona_name") or "Ramesh Sharma"))
            pc_intel = pc.get("extracted_intel", {}) or {}
            mid_logs = pc_intel.get("mid_call_logs", []) or pc.get("mid_call_logs", [])
            live_chips = T.intel_chips_html(pc_intel, mid_logs) or (
                "<span class='muted'>Stalling in progress. Waiting for payment details.</span>"
            )
            live_items.append(
                '<div class="live-item"><div class="live-meta">'
                f'<span>Call <a class="live-link" href="/dashboard/calls/{pc_path}">{html.escape(pcid)}</a></span>'
                f"<span>Persona: {persona}</span></div>"
                f'<div class="chips">{live_chips}</div></div>'
            )
        live_banner_html = (
            '<section id="live-honeypot-banner" class="m3-card salmon">'
            '<div class="live-head"><span class="pulse"></span><strong>LIVE HONEYPOT ACTIVE</strong>'
            "<span>Ramesh AI is stalling a suspected scammer right now</span></div>"
            + "".join(live_items)
            + "</section>"
        )

    # Family circle: avatar bubbles (everyone, caretakers, then dependents)
    family_topology = get_family_registry().get_family_topology()
    caretakers_topo = family_topology.get("caretakers", [])
    dependents_topo = family_topology.get("dependents", [])
    bubbles = [
        T.family_bubble(
            "/dashboard", "All family", "All", "All", "#CFE5CF",
            active=not caretaker_id and not dependent_id,
        )
    ]
    for idx, ct in enumerate(caretakers_topo):
        bubbles.append(
            T.family_bubble(
                f"/dashboard?caretaker_id={quote(str(ct['caretaker_id']), safe='')}",
                ct["name"], T.short_label(ct["name"]), T.initials(ct["name"]),
                T.CARETAKER_FILL, active=caretaker_id == ct["caretaker_id"], kind="caretaker",
            )
        )
    if caretakers_topo and dependents_topo:
        bubbles.append('<span class="bubble-sep"></span>')
    for idx, dp in enumerate(dependents_topo):
        is_kid = str(dp.get("role", "")).lower() == "child"
        bubbles.append(
            T.family_bubble(
                f"/dashboard?dependent_id={quote(str(dp['dependent_id']), safe='')}",
                dp["name"], T.short_label(dp["name"]), T.initials(dp["name"]),
                T.KID_FILL if is_kid else T.ELDER_FILL,
                active=dependent_id == dp["dependent_id"], kind="dependent",
            )
        )
    filter_style = "" if (caretaker_id or dependent_id) else ' style="display:none"'
    family_row_html = f'<div class="m3-family-row"{filter_style}>{"".join(bubbles)}</div>'

    # Overview cards: who protects whom, scam calls this week, portal shortcuts
    week_buckets, week_total = T.weekly_scam_buckets(
        all_calls, datetime.now(IST).date(), IST, _parse_timestamp
    )
    top_bento_html = (
        '<div class="bento-2x2">'
        f'<section class="m3-card"><h2>Family Network Topology</h2>{T.topology_svg(caretakers_topo, dependents_topo)}</section>'
        '<section class="m3-card"><h2>Live Scam Detection Activity</h2>'
        f"{T.activity_svg(week_buckets)}</section>"
        "</div>"
    )

    tiles_html = (
        '<section class="m3-card tiles-card">'
        '<a class="tile" href="https://sancharsaathi.gov.in/sfc/" target="_blank" rel="noopener noreferrer">'
        '<span>DoT Chakshu<br>Portal</span><span class="arr">&rarr;</span></a>'
        '<a class="tile" href="https://cybercrime.gov.in" target="_blank" rel="noopener noreferrer">'
        '<span>National Cyber<br>Crime 1930</span><span class="arr">&rarr;</span></a>'
        "</section>"
    )

    linked_clusters = scam_intel["linked_clusters"]
    intel_banner_html = ""
    if linked_clusters:
        intel_rows = []
        for cl in linked_clusters[:4]:
            k_label = "UPI" if cl["kind"] == "upi" else "Bank A/C"
            intel_rows.append(
                '<div class="linked-row">'
                f'<span class="intel-tag">{k_label}: {html.escape(cl["identifier"])}</span>'
                f'<span class="muted">{cl["call_count"]} linked calls</span></div>'
            )
        intel_banner_html = (
            '<section class="m3-card">'
            '<div class="row-between" style="margin-bottom:8px"><h2>Syndicate Links</h2>'
            '<a class="btn-soft" href="/dashboard/intelligence" style="padding:6px 12px;font-size:12px">View all &rarr;</a></div>'
            + "".join(intel_rows)
            + "</section>"
        )

    total_pages = max(1, (total_calls + limit - 1) // limit) if total_calls > 0 else 1
    start_num = (page - 1) * limit + 1 if total_calls > 0 else 0
    end_num = min(page * limit, total_calls)

    if not calls:
        cards_html = (
            '<div class="m3-card empty"><h3>No calls handled yet</h3>'
            '<p class="muted">Protection is active. Screened calls show up here as they happen.</p></div>'
        )
    else:
        cards_html = "".join(T.call_card_html(c) for c in calls)

    def _page_href(target_page: int) -> str:
        params = {"page": target_page, "limit": limit}
        if verdict:
            params["verdict"] = verdict
        if dependent_id:
            params["dependent_id"] = dependent_id
        if caretaker_id:
            params["caretaker_id"] = caretaker_id
        return "/dashboard?" + urlencode(params)

    prev_link = (
        f'<a class="btn" href="{html.escape(_page_href(page - 1))}">Previous</a>'
        if page > 1 else '<span class="btn disabled">Previous</span>'
    )
    next_link = (
        f'<a class="btn" href="{html.escape(_page_href(page + 1))}">Next</a>'
        if page < total_pages else '<span class="btn disabled">Next</span>'
    )
    pagination_html = (
        '<div class="pager"><span class="muted">'
        f"Showing {start_num}-{end_num} of {total_calls} calls (page {page} of {total_pages})</span>"
        f'<span class="actions">{prev_link}{next_link}</span></div>'
    )

    page_script = """
    (function() {
        window.confirmSafe = function(callId) {
            fetch('/api/calls/' + encodeURIComponent(callId) + '/verify_son_safe', {method: 'POST'})
                .then(function(r) { return r.json(); })
                .then(function() { window.location.reload(); })
                .catch(function(err) { console.error("Verify safe error:", err); });
        };
        var params = new URLSearchParams(window.location.search);
        var isLive = params.get("live") === "1";
        if (isLive && window.EventSource) {
            var es = new EventSource('/dashboard/sse');
            ['family_verification_pending', 'family_verified_safe', 'legitimate_caller_approved', 'syndicate_match_detected']
                .forEach(function(name) { es.addEventListener(name, function() { window.location.reload(); }); });
        }
        var hasPending = Boolean(document.getElementById("live-honeypot-banner") || document.body.innerHTML.includes('"status": "pending"') || document.body.innerHTML.includes('status="pending"'));
        if (isLive || hasPending) {
            setTimeout(function() { window.location.reload(); }, 4000);
        }
    })();
    """

    body_html = (
        f'<div class="stage-top"><h1>Dashboard</h1>{family_row_html}</div>'
        f"{live_banner_html}{top_bento_html}"
        '<div class="bento-bottom">'
        f'<section class="m3-card"><h2>Intercepted Scam Calls</h2><div class="m3-bento-grid">{cards_html}</div>{pagination_html}</section>'
        f'<div class="right-stack">{tiles_html}{intel_banner_html}</div>'
        "</div>"
    )
    return HTMLResponse(
        content=T.page_shell("Rakshak AI · Family Hub", body_html, active="home", script=page_script)
    )


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

    from app.core import gui_theme as T

    cls, badge_text, glyph = T.verdict_style(v)
    intel_chips = T.intel_chips_html(intel)
    intel_block = f'<div class="chips">{intel_chips}</div>' if intel_chips else ""

    dep_name_detail = str(record.get("dependent_name") or "").strip()
    meta_html = f"<span>Caller ID: {caller}</span>"
    if dep_name_detail:
        meta_html += f"<span>For {html.escape(dep_name_detail)}</span>"

    rec_url_raw = str(record.get("call_recording_url") or "").strip()
    rec_link_html = ""
    if rec_url_raw.lower().startswith(("http://", "https://")):
        rec_link_html = (
            f'<a class="btn-soft" href="{html.escape(rec_url_raw)}" target="_blank" '
            'rel="noopener noreferrer">Open audio</a>'
        )

    turns_html = []
    for turn in transcript:
        raw_role = str(turn.get("role", "unknown"))
        escaped_role = html.escape(raw_role.title())
        content = html.escape(str(turn.get("content", "")))
        role_class = "caller-turn" if raw_role.lower() in ("caller", "user") else "agent-turn"
        turns_html.append(f'<div class="turn {role_class}"><strong>{escaped_role}:</strong> {content}</div>')
    transcript_content = "".join(turns_html) if turns_html else "<p class='muted'>No dialogue turns recorded.</p>"

    # Evidence: Chakshu packet, Report Suspect packets, review and confirm
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
            '<div class="ev-status confirmed">Confirmed by Family'
            f'{f" · {confirmed_at}" if confirmed_at else ""}. Filing stays manual; nothing is auto-submitted.</div>'
        )
    else:
        status_badge_html = (
            '<div class="ev-status draft">Draft. Review with your family member, then confirm. '
            "Nothing is auto-submitted to any portal.</div>"
        )

    suspect_cards = []
    for idx, pkt in enumerate(suspect_packets):
        pkt_json_esc = html.escape(json.dumps(pkt.to_dict(), indent=2, ensure_ascii=False))
        kind_esc = html.escape(pkt.kind.upper())
        val_norm_esc = html.escape(pkt.value_normalized)
        val_raw_esc = html.escape(pkt.value_raw)
        quote_line = f'<p class="muted">Quote: "{html.escape(pkt.quote)}"</p>' if pkt.quote else ""
        elicit_line = f'<p class="muted">Tactic: {html.escape(pkt.elicitation)}</p>' if pkt.elicitation else ""
        suspect_cards.append(
            '<div class="packet-item"><div class="packet-row">'
            f'<span class="intel-tag">{kind_esc}: {val_norm_esc}</span>'
            '<div class="copy-group">'
            f'<button type="button" class="btn-copy" data-copy-text="{val_norm_esc}" onclick="copyBtnText(this)">Copy {kind_esc}</button>'
            f'<button type="button" class="btn-copy" data-copy-target="suspect-pkt-{idx}" onclick="copyFromTarget(this)">Copy packet</button>'
            "</div></div>"
            f'<p class="muted">Heard as: {val_raw_esc} · {html.escape(pkt.status)}</p>{quote_line}{elicit_line}'
            f'<details><summary>Packet details</summary><pre id="suspect-pkt-{idx}" class="packet-pre">{pkt_json_esc}</pre></details>'
            "</div>"
        )
    suspect_packets_html = (
        "".join(suspect_cards) if suspect_cards else "<p class='muted'>No suspect identifiers captured in this call.</p>"
    )

    # Cross-linked calls sharing the same UPI ID or bank account (overview sessions only)
    linked_calls_card_html = ""
    if not auth:
        all_calls, _ = store.get_calls(verdict=None, page=1, limit=500)
        scam_intel = build_scam_intelligence(all_calls)
        shared_links = scam_intel["shared_by_call_id"].get(call_id, [])
        if shared_links:
            shared_rows = []
            for item in shared_links:
                k_label = "UPI ID" if item["kind"] == "upi" else "Bank account"
                peer_links = " ".join(
                    f'<a class="live-link" href="/dashboard/calls/{html.escape(quote(p["call_id"], safe=""))}">'
                    f'{html.escape(p["call_id"])} ({html.escape(p["caller_number"])})</a>'
                    for p in item["peer_calls"]
                )
                shared_rows.append(
                    '<div class="linked-row">'
                    f'<span class="intel-tag">{k_label}: {html.escape(item["identifier"])}</span>'
                    f'<span class="muted">also seen on</span>{peer_links}</div>'
                )
            linked_calls_card_html = (
                '<section class="m3-card" id="linked-scam-intelligence">'
                '<h2>Same scammer on other calls</h2>'
                + "".join(shared_rows)
                + '<div style="margin-top:10px"><a class="btn-soft" href="/dashboard/intelligence">Scam Intelligence</a></div>'
                "</section>"
            )

    hero_class = "m3-card salmon" if cls == "scam" else "m3-card"
    body_html = (
        '<div style="max-width:760px">'
        f"{back_link}"
        f'<section class="{hero_class}">'
        f'<div class="verdict"><span class="warn">{glyph}</span>{badge_text}'
        f'<span class="dur">{duration:.0f}s</span></div>'
        f'<h1 style="font-size:24px;margin:10px 0 6px">{summary}</h1>'
        f'<div class="card-meta" style="margin-bottom:10px">{meta_html}</div>'
        f"{intel_block}"
        '<div class="m3-waveform-player" style="margin:14px 0">'
        f'<span class="play">&#9654;</span>{T.bars_html(call_id)}'
        f'<span class="player-time">{duration:.0f}s</span>{rec_link_html}</div>'
        f'<div class="actions"><a class="btn" href="/dashboard/report/{safe_call_path}{escaped_auth}" target="_blank">Draft 1930 report</a></div>'
        "</section>"
        '<section class="m3-card" id="evidence-section">'
        "<h2>Evidence and reporting packets</h2>"
        f"{status_badge_html}"
        f'<form method="post" action="/dashboard/calls/{safe_call_path}/confirm{escaped_auth}" class="confirm-form">'
        "<p>Review the captured details with your family member, confirm here, then copy a packet and file it yourself on Chakshu or cybercrime.gov.in.</p>"
        '<button type="submit" class="btn-confirm">Review and Confirm Evidence</button></form>'
        '<div class="portal-links">'
        '<a class="btn-soft" href="https://sancharsaathi.gov.in/sfc/" target="_blank" rel="noopener noreferrer">Report on Chakshu (sancharsaathi.gov.in)</a>'
        '<a class="btn-soft" href="https://cybercrime.gov.in" target="_blank" rel="noopener noreferrer">National Cybercrime Portal (cybercrime.gov.in)</a>'
        "</div>"
        "<h3 style=\"font-size:15px;margin-top:6px\">DoT Sanchar Saathi (Chakshu) packet</h3>"
        '<div class="packet-item"><div class="packet-row">'
        f"<strong>{chakshu_category_escaped}</strong>"
        '<div class="copy-group">'
        '<button type="button" class="btn-copy" data-copy-target="chakshu-summary" onclick="copyFromTarget(this)">Copy Chakshu summary</button>'
        '<button type="button" class="btn-copy" data-copy-target="chakshu-json" onclick="copyFromTarget(this)">Copy Chakshu packet</button>'
        "</div></div>"
        f'<p class="muted">Integrity SHA-256: <code>{ev_hash_escaped}</code></p>'
        f'<pre id="chakshu-summary" class="packet-pre">{chakshu_summary_escaped}</pre>'
        f'<details><summary>Full packet</summary><pre id="chakshu-json" class="packet-pre">{chakshu_json_escaped}</pre></details>'
        "</div>"
        f'<h3 style="font-size:15px;margin-top:18px">Report Suspect packets ({len(suspect_packets)})</h3>'
        f"{suspect_packets_html}</section>"
        f"{linked_calls_card_html}"
        f'<section class="m3-card"><h2>Call transcript ({duration:.0f}s)</h2>{transcript_content}</section>'
        "</div>"
    )

    detail_script = """
    (function() {
        var params = new URLSearchParams(window.location.search);
        var isLive = params.get("live") === "1";
        var isPending = __PENDING__;
        if (isLive || isPending) {
            setTimeout(function() { window.location.reload(); }, 4000);
        }
    })();
    """.replace("__PENDING__", is_pending_js)

    return HTMLResponse(
        content=T.page_shell(
            f"Call {call_id} · Rakshak AI", body_html, active="home",
            rail=not auth, script=detail_script,
        )
    )



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

    from app.core import gui_theme as T

    if not clusters:
        clusters_html = (
            '<section class="m3-card"><p class="muted">'
            "No UPI IDs or bank accounts extracted yet.</p></section>"
        )
    else:
        cluster_cards = []
        for cl in clusters:
            kind_label = "UPI ID" if cl["kind"] == "upi" else "Bank Account"
            ident_esc = html.escape(cl["identifier"])
            status_pill = (
                f'<span class="pill">{cl["call_count"]} calls linked</span>'
                if cl["linked_across_calls"] else '<span class="pill">1 call</span>'
            )
            call_rows = []
            for c_item in cl["calls"]:
                cid_esc = html.escape(c_item["call_id"])
                cid_path = html.escape(quote(c_item["call_id"], safe=""))
                cnum_esc = html.escape(c_item["caller_number"])
                csum_esc = html.escape(c_item["summary"] or "No summary")
                call_rows.append(
                    '<div class="call-row">'
                    f'<a href="/dashboard/calls/{cid_path}" class="call-link">{cid_esc}</a> · '
                    f'<strong>{cnum_esc}</strong> · <span class="summary-inline">{csum_esc}</span></div>'
                )
            cluster_cards.append(
                '<section class="m3-card m3-syndicate-card">'
                '<div class="cluster-head">'
                f'<span class="intel-tag">{kind_label}: {ident_esc}</span>'
                '<div class="copy-group">'
                f"{status_pill}"
                f'<button type="button" class="btn-copy" data-copy-text="{ident_esc}" onclick="copyBtnText(this)">Copy {kind_label}</button>'
                "</div></div>"
                f'<div class="call-list">{"".join(call_rows)}</div></section>'
            )
        clusters_html = "".join(cluster_cards)

    body_html = (
        '<h1>Scam Intelligence</h1>'
        '<p class="muted" style="margin:-8px 0 18px">Calls that share the same UPI ID or bank account.</p>'
        f"{clusters_html}"
    )
    return HTMLResponse(content=T.page_shell("Scam Intelligence · Rakshak AI", body_html, active="intel"))


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
