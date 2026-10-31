"""
Material You 3 Expressive theme for the GuardianLine family web dashboard.
File: app/core/gui_theme.py

Matches the approved Option 5 reference mockup:
- Full-height left navigation rail on a calm sage-tinted canvas (#EEF3EC).
- 2x2 Bento Grid of crisp white cards (#FFFFFF):
  1. Top-Left: Family Network Topology (radial graph with illustrated portrait avatars).
  2. Top-Right: Live Scam Detection Activity (Wave Analytics purple spline chart).
  3. Bottom-Left: Intercepted Scam Calls (compact coral-salmon cards with waveform & 1930 button).
  4. Bottom-Right: DoT Chakshu Portal & National Cyber Crime 1930 lavender action tiles + syndicate links.
"""

import hashlib
import html
import math
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

AVATAR_COLORS = ["#D7ECD5", "#E5DBF7", "#F9DFC6", "#F7E9BC", "#D6E6F6", "#F5D7E4"]
CARETAKER_FILL = "#E5DBF7"
CARETAKER_STROKE = "#9A82DB"
ELDER_FILL = "#F9DFC6"
ELDER_STROKE = "#8EB892"
KID_FILL = "#D7ECD5"
KID_STROKE = "#7FA883"

M3_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --forest:#2B4A32;--forest-soft:#3C5E44;--ink:#1B1C1A;--muted:#5F6B61;
  --canvas:#EEF3EC;--surface:#FFFFFF;--mint:#E6F0E4;--lav:#E8DDF8;--lav-ink:#261952;
  --salmon:#FBCBBD;--salmon-ink:#2C120C;--alert:#B3261E;--line:#E2EAE0;
}
body{
  font-family:"Google Sans","Plus Jakarta Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  color:var(--ink);line-height:1.45;min-height:100vh;
  background:linear-gradient(125deg,#D5E3D5 0%,#E4EAE3 45%,#E4DAF5 100%);
  padding:18px;
}
a{color:inherit;text-decoration:none}
.shell{
  display:grid;grid-template-columns:248px minmax(0,1fr);gap:24px;
  max-width:1420px;min-height:calc(100vh - 36px);margin:0 auto;
  background:var(--canvas);border-radius:32px;padding:22px 26px 26px 22px;
  box-shadow:0 20px 60px rgba(24,38,28,.10);border:1px solid rgba(255,255,255,.7);
  align-items:stretch;
}
.shell.no-rail{grid-template-columns:minmax(0,1fr);max-width:820px}
.m3-nav-rail{
  background:#E6EFE4;border-radius:24px;padding:22px 14px;
  display:flex;flex-direction:column;min-height:calc(100vh - 80px);height:100%;
}
.rail-inner{
  display:flex;flex-direction:column;gap:6px;position:sticky;top:22px;
  min-height:calc(100vh - 124px);flex:1;
}
.brand{
  display:flex;align-items:center;gap:11px;font-size:19px;font-weight:600;
  padding:4px 12px 20px;color:#1B2E1E;letter-spacing:-.01em;
}
.brand .mark{
  width:32px;height:32px;border-radius:10px;background:var(--forest);color:#fff;
  display:flex;align-items:center;justify-content:center;flex:none;
}
.rail-link{
  display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:14px;
  font-size:14.5px;font-weight:500;color:#2E3D31;transition:background .15s;
}
.rail-link svg{width:19px;height:19px;flex:none;color:#3B523F}
.rail-link:hover{background:rgba(255,255,255,.65)}
.rail-link.active{background:#CBE0CA;color:#142818;font-weight:600}
.rail-link.active svg{color:#142818}
.rail-sep{height:1px;background:#D3E0D1;margin:10px 12px}
.rail-foot{
  margin-top:auto;background:rgba(255,255,255,.65);border-radius:18px;
  padding:14px 16px;font-size:12.5px;color:#2E3D31;border:1px solid #D5E2D3;
}
.rail-foot strong{display:flex;align-items:center;gap:6px;font-size:13.5px;font-weight:600;color:#16301B;margin-bottom:2px}
.rail-foot .dot{width:8px;height:8px;border-radius:50%;background:#2E7D32;display:inline-block}
.stage{min-width:0;display:flex;flex-direction:column}
.stage-top{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:18px}
h1{font-size:26px;font-weight:500;letter-spacing:-.015em;color:#1B1C1A}
h2{font-size:16px;font-weight:600;color:#1B1C1A;margin-bottom:10px}
.muted{color:var(--muted);font-size:13px}
.m3-card{
  background:var(--surface);border-radius:22px;padding:20px 22px;
  border:1px solid var(--line);box-shadow:0 2px 8px rgba(20,36,24,.025);
}
.m3-card.salmon{background:var(--salmon);color:var(--salmon-ink);border-color:transparent}
.row-between{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}

/* Compact Family Filter Bar */
.m3-family-row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.m3-family-bubble{
  display:inline-flex;align-items:center;gap:7px;padding:5px 11px 5px 6px;
  border-radius:999px;background:#fff;border:1px solid var(--line);
  font-size:12.5px;font-weight:500;color:#2E3D31;transition:all .15s;
}
.m3-family-bubble:hover{border-color:#9EB8A0;background:#F7FAF6}
.m3-family-bubble .avatar{
  width:24px;height:24px;border-radius:50%;display:inline-flex;align-items:center;
  justify-content:center;font-size:10px;font-weight:700;color:#23332A;
}
.m3-family-bubble.active{background:var(--forest);color:#fff;border-color:var(--forest)}
.m3-family-bubble.active .name{font-weight:600;color:#fff}
.bubble-sep{width:1px;height:18px;background:var(--line);margin:0 2px}

/* Reference 2x2 Bento Grid */
.bento-2x2{
  display:grid;grid-template-columns:1.02fr 1.18fr;gap:18px;margin-bottom:18px;
}
.bento-bottom{
  display:grid;grid-template-columns:1.35fr 0.85fr;gap:18px;align-items:start;
}
.right-stack{display:flex;flex-direction:column;gap:18px}
.tiles-card{display:flex;flex-direction:column;gap:14px}
.tile{
  display:flex;flex-direction:column;justify-content:space-between;min-height:108px;
  background:var(--lav);color:var(--lav-ink);border-radius:18px;padding:18px 20px;
  font-size:16px;font-weight:600;line-height:1.3;transition:transform .12s,filter .12s;
}
.tile:hover{filter:brightness(.97);transform:translateY(-1px)}
.tile .arr{align-self:flex-end;font-size:18px;font-weight:500}

/* Scam Call Cards */
.m3-bento-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:14px}
.call-card{
  background:var(--salmon);color:var(--salmon-ink);border-radius:22px;padding:18px 20px;
  display:flex;flex-direction:column;gap:9px;min-width:0;word-wrap:break-word;
}
.call-card.genuine{background:#DCEPDO;background:#DCEUD8;background:#DCEFD9;color:#14301A}
.call-card.unsure{background:#EBF0EA;color:#26302A}
.verdict{display:flex;align-items:center;gap:7px;font-size:11.5px;font-weight:700;letter-spacing:.03em}
.verdict .warn{color:var(--alert);font-size:15px}
.call-card.genuine .verdict .warn{color:#2E7D32}
.verdict .dur{margin-left:auto;font-weight:600;opacity:.75}
.card-title{
  font-size:16.5px;font-weight:600;line-height:1.3;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
}
.card-meta{font-size:13px;opacity:.9}
.card-meta span+span::before{content:" · "}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.intel-tag{
  font-family:"JetBrains Mono",Consolas,monospace;font-size:11.5px;font-weight:600;
  padding:5px 11px;border-radius:999px;background:rgba(255,255,255,.62);
  border:1px solid rgba(62,26,18,.14);color:inherit;word-break:break-all;
}
.m3-card:not(.salmon) .intel-tag,.call-card.genuine .intel-tag{border-color:var(--line);background:#F5F8F4}
.m3-waveform-player{
  display:flex;align-items:center;gap:10px;background:rgba(255,255,255,.48);
  border-radius:18px;padding:8px 12px;margin-top:2px;
}
.play{
  width:36px;height:36px;border-radius:50%;background:var(--forest);color:#fff;flex:none;
  display:flex;align-items:center;justify-content:center;font-size:13px;
}
.bars{display:flex;align-items:center;gap:3px;flex:1;height:28px;overflow:hidden}
.bars i{display:block;width:3px;border-radius:2px;background:var(--forest);opacity:.82}
.player-time{font-size:11.5px;font-weight:600;opacity:.75;flex:none}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:2px}
.btn,.btn-soft,.btn-copy,.btn-confirm{
  display:inline-flex;align-items:center;justify-content:center;border:none;cursor:pointer;
  font:inherit;font-size:13px;font-weight:600;border-radius:999px;padding:10px 18px;
}
.btn,.btn-confirm{background:var(--forest);color:#fff}
.btn:hover,.btn-confirm:hover{background:var(--forest-soft)}
.btn.block{width:100%}
.btn-soft{background:rgba(255,255,255,.72);color:var(--forest);border:1px solid rgba(43,74,50,.22)}
.btn-copy{background:#fff;color:var(--forest);border:1px solid var(--line);font-size:12px;padding:6px 14px}
.pill{display:inline-block;font-size:11.5px;font-weight:600;padding:4px 11px;border-radius:999px;background:#fff;color:var(--forest)}
.pill.ok{background:#D8EBD6;color:#14301A}
.pill.wait{background:#FFF1C9;color:#5B4300}
.live-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.pulse{width:10px;height:10px;border-radius:50%;background:var(--alert);animation:pulse 1.6s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(179,38,30,.5)}70%{box-shadow:0 0 0 10px rgba(179,38,30,0)}100%{box-shadow:0 0 0 0 rgba(179,38,30,0)}}
.live-item{background:rgba(255,255,255,.6);border-radius:16px;padding:10px 14px;margin-top:8px}
.live-meta{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;font-size:12.5px;margin-bottom:6px}
.live-link{font-family:monospace;font-weight:700}
.linked-row{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;padding:7px 0;border-top:1px solid var(--line);font-size:12.5px}
.linked-row:first-of-type{border-top:none}
.pager{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
.pager .btn.disabled{background:#E8EFE7;color:#8AA08D;pointer-events:none}
.empty{text-align:center;padding:36px 20px;grid-column:1/-1}
.empty h3{font-size:17px;font-weight:600;margin-bottom:4px}
.back-link{display:inline-block;margin-bottom:14px;font-size:14px;font-weight:600;color:var(--forest)}
.turn{padding:12px 16px;border-radius:18px;margin-bottom:8px;font-size:14px;max-width:88%}
.turn.caller-turn{background:#FDE3DB;color:var(--salmon-ink)}
.turn.agent-turn{background:#E1EFDF;color:#14301A;margin-left:auto}
.turn strong{display:block;font-size:11px;letter-spacing:.04em;text-transform:uppercase;opacity:.7;margin-bottom:2px}
details{background:#fff;border-radius:18px;padding:12px 16px;margin-top:10px;border:1px solid var(--line)}
details summary{cursor:pointer;font-weight:600;font-size:14px}
.packet-pre{
  font-family:"JetBrains Mono",Consolas,monospace;font-size:11px;white-space:pre-wrap;word-break:break-all;
  background:var(--mint);padding:12px;border-radius:14px;margin-top:10px;
}
.packet-item{margin-top:12px}
.packet-row{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.copy-group{display:flex;gap:6px;flex-wrap:wrap}
.confirm-form{background:var(--mint);border-radius:18px;padding:16px;margin:12px 0}
.confirm-form p{font-size:13px;color:var(--muted);margin-bottom:10px}
.portal-links{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.ev-status{padding:10px 14px;border-radius:14px;font-size:13px;font-weight:600}
.ev-status.draft{background:#FFF1C9;color:#5B4300}
.ev-status.confirmed{background:#D8EBD6;color:#14301A}
.cluster-head{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.call-row{padding:10px 0;border-top:1px solid var(--line);font-size:14px}
.call-link{font-family:monospace;font-weight:700;color:var(--forest)}
.summary-inline{color:var(--muted)}
svg text{font-family:inherit}
@media (max-width:1024px){
  .shell{grid-template-columns:1fr;padding:16px}
  .m3-nav-rail{min-height:auto;height:auto;border-radius:20px;padding:12px}
  .rail-inner{position:static;min-height:auto;flex-direction:row;flex-wrap:wrap;align-items:center}
  .rail-sep,.rail-foot{display:none}
  .brand{padding:4px 10px}
  .bento-2x2,.bento-bottom{grid-template-columns:1fr}
}
"""

M3_JS = """
function copyFromTarget(btn){
  var el=document.getElementById(btn.getAttribute("data-copy-target"));
  if(!el)return;
  var text=el.innerText||el.textContent;
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(text);}
  var orig=btn.innerText;btn.innerText="Copied";setTimeout(function(){btn.innerText=orig;},1500);
}
function copyBtnText(btn){
  var text=btn.getAttribute("data-copy-text")||"";
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(text);}
  var orig=btn.innerText;btn.innerText="Copied";setTimeout(function(){btn.innerText=orig;},1500);
}
"""


def esc(value: Any) -> str:
    return html.escape(str(value))


def short_label(name: Any) -> str:
    """`Rajesh Sharma (Dad)` -> `Dad`; `Aarav Sharma (Kid)` -> `Aarav`."""
    text = str(name or "").strip()
    if "(" in text and ")" in text:
        inner = text[text.index("(") + 1:text.rindex(")")].strip()
        if inner and inner.lower() not in ("kid", "child"):
            return inner
    return text.split()[0] if text else "Family"


def initials(name: Any) -> str:
    base = str(name or "").split("(")[0].strip()
    parts = [p for p in base.split() if p]
    if not parts:
        return "G"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def avatar_color(index: int) -> str:
    return AVATAR_COLORS[index % len(AVATAR_COLORS)]


def nav_rail(active: str = "home") -> str:
    icons = {
        "home": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5L12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1v-9.5z"/></svg>',
        "dash": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>',
        "intel": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><path d="M8.5 7.5L11 15.5M15.5 7.5L13 15.5M9 6h6"/></svg>',
        "chakshu": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
        "cyber": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    }
    shield_mark = (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.3" '
        'stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
        '<path d="M9 12l2 2 4-4"/></svg>'
    )

    def link(key: str, label: str, href: str, is_active: bool = False, external: bool = False) -> str:
        cls = "rail-link active" if is_active else "rail-link"
        extra = ' target="_blank" rel="noopener noreferrer"' if external else ""
        icon = icons.get(key, "")
        return f'<a class="{cls}" href="{esc(href)}"{extra}>{icon}<span>{esc(label)}</span></a>'

    return (
        '<nav class="m3-nav-rail"><div class="rail-inner">'
        f'<div class="brand"><span class="mark">{shield_mark}</span>Rakshak AI</div>'
        + link("home", "Home", "/dashboard", is_active=(active == "home"))
        + link("dash", "Dashboard", "/dashboard", is_active=False)
        + link("intel", "Syndicates", "/dashboard/intelligence", is_active=(active == "intel"))
        + '<div class="rail-sep"></div>'
        + link("chakshu", "Chakshu (DoT)", "https://sancharsaathi.gov.in/sfc/", external=True)
        + link("cyber", "Cybercrime 1930", "https://cybercrime.gov.in", external=True)
        + '<div class="rail-foot"><strong><span class="dot"></span>Shield Active</strong>Protecting your family circle</div>'
        + "</div></nav>"
    )


def page_shell(title: str, body: str, active: str = "home", rail: bool = True, script: str = "") -> str:
    shell_cls = "shell" if rail else "shell no-rail"
    rail_html = nav_rail(active) if rail else ""
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{esc(title)}</title><style>{M3_CSS}</style>"
        f"<script>{M3_JS}</script></head><body>"
        f'<div class="{shell_cls}">{rail_html}<main class="stage">{body}</main></div>'
        f"<script>{script}</script></body></html>"
    )


def family_bubble(href: str, full_name: str, label: str, initial_text: str, color: str,
                  active: bool = False, kind: str = "") -> str:
    cls = "m3-family-bubble"
    if kind:
        cls += f" {kind}"
    if active:
        cls += " active"
    return (
        f'<a href="{esc(href)}" class="{cls}" title="{esc(full_name)}">'
        f'<span class="avatar" style="background:{color}">{esc(initial_text)}</span>'
        f'<span class="name">{esc(label)}</span></a>'
    )


def bars_html(seed: str, count: int = 30) -> str:
    digest = hashlib.sha256(str(seed).encode("utf-8")).digest()
    heights = []
    for i in range(count):
        byte = digest[i % len(digest)]
        heights.append(6 + (byte % 20))
    return '<span class="bars">' + "".join(f'<i style="height:{h}px"></i>' for h in heights) + "</span>"


def safe_duration(value: Any) -> float:
    try:
        number = float(value)
        return number if number >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def intel_chips_html(intel: Dict[str, Any], mid_logs: Optional[Iterable[Any]] = None) -> str:
    chips: List[str] = []
    for key, label, cls in (
        ("upi_ids", "UPI", "upi"),
        ("bank_accounts", "A/C", "acc"),
        ("ifsc_codes", "IFSC", "ifsc"),
        ("phone_numbers", "Ph", "ph"),
        ("links", "Link", "lnk"),
    ):
        for value in intel.get(key, []) or []:
            chips.append(f'<span class="intel-tag m3-tonal-chip {cls}">{label}: {esc(value)}</span>')
    existing = " ".join(chips)
    for entry in mid_logs or []:
        if isinstance(entry, dict):
            value = str(entry.get("normalized_value") or entry.get("value_as_heard") or entry.get("value") or "")
            kind = str(entry.get("type") or entry.get("kind") or "intel").upper()
            if value and esc(value) not in existing:
                chips.append(f'<span class="intel-tag m3-tonal-chip upi">{esc(kind)}: {esc(value)}</span>')
    return "".join(chips)


def verdict_style(verdict: str) -> Tuple[str, str, str]:
    """Returns (css_class, badge_text, glyph)."""
    v = (verdict or "unsure").lower()
    if v == "scam":
        return "scam", "SUSPECTED SCAM", "&#9888;"
    if v in ("genuine", "safe_delivery", "legitimate_verified"):
        return "genuine", "VERIFIED DELIVERY" if "delivery" in v else "GENUINE", "&#10003;"
    return "unsure", "UNSURE", "?"


def call_card_html(c: Dict[str, Any]) -> str:
    c_id_raw = str(c.get("call_id", ""))
    c_id = esc(c_id_raw)
    c_path = esc(quote(c_id_raw, safe=""))
    caller = esc(c.get("caller_number") or "Unknown / Withheld")
    cls, badge_text, glyph = verdict_style(str(c.get("verdict", "unsure")))
    duration = safe_duration(c.get("duration"))
    summary = esc(c.get("summary") or "No summary recorded.")
    chips = intel_chips_html(c.get("extracted_intel", {}) or {})
    chips_block = f'<div class="chips">{chips}</div>' if chips else ""

    dep_name = str(c.get("dependent_name") or "").strip()
    meta = f"<span>Caller ID: {caller}</span>"
    if dep_name:
        meta += f"<span>For {esc(short_label(dep_name))}</span>"

    fam_status = str(c.get("family_verification_status") or "NONE").upper()
    fam_html = ""
    if fam_status == "CONFIRMED_SAFE":
        fam_html = '<div><span class="pill ok">AMIT CONFIRMED SAFE IN PUNE</span></div>'
    elif fam_status == "PENDING":
        fam_html = (
            '<div class="actions"><span class="pill wait">VERIFYING AMIT SAFE...</span>'
            f'<button type="button" class="btn-soft" data-call-id="{c_id}" '
            'onclick="confirmSafe(this.dataset.callId)">Simulate Amit SAFE Reply</button></div>'
        )

    return (
        f'<article class="call-card {cls}">'
        f'<div class="verdict"><span class="warn">{glyph}</span>{badge_text}'
        f'<span class="dur">{duration:.0f}s</span></div>'
        f'<h3 class="card-title">{summary}</h3>'
        f'<div class="card-meta">{meta}</div>'
        f"{fam_html}{chips_block}"
        f'<a class="m3-waveform-player" href="/dashboard/calls/{c_path}">'
        f'<span class="play">&#9654;</span>{bars_html(c_id_raw)}'
        f'<span class="player-time">{duration:.0f}s</span></a>'
        f'<div class="actions">'
        f'<a class="btn block" href="/dashboard/calls/{c_path}">File 1930 &amp; Chakshu Report</a>'
        f"</div></article>"
    )


def _portrait_group(x: float, y: float, r: float, label: str, fill: str, stroke: str) -> str:
    """Draws an illustrated Material You portrait avatar at (x, y) with radius r."""
    low = label.lower()
    is_grandpa = "grandpa" in low or "ramesh" in low
    is_grandma = "grandma" in low or "kamla" in low or "sunita" in low
    is_mom = "mom" in low or "priya" in low or "ananya" in low

    hair_color = "#D8D8D8" if (is_grandpa or is_grandma) else "#2B211B"
    skin = "#E8B48A" if not is_mom else "#F0C097"
    shirt = "#34593B" if not is_mom else "#6E4F9E"
    if is_grandpa:
        shirt = "#9E7B4F"
    elif is_grandma:
        shirt = "#8B5E83"

    clip_id = f"clip_{int(x)}_{int(y)}_{abs(hash(label)) % 999}"
    parts = [
        f'<defs><clipPath id="{clip_id}"><circle cx="{x}" cy="{y}" r="{r - 1.5}"/></clipPath></defs>',
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2.2"/>',
        f'<g clip-path="url(#{clip_id})">',
        # Shoulders
        f'<ellipse cx="{x}" cy="{y + r * 0.85}" rx="{r * 0.72}" ry="{r * 0.48}" fill="{shirt}"/>',
    ]
    # Hair back for women
    if is_mom or is_grandma:
        parts.append(f'<circle cx="{x}" cy="{y - r * 0.08}" r="{r * 0.50}" fill="{hair_color}"/>')
    # Head
    parts.append(f'<circle cx="{x}" cy="{y - r * 0.08}" r="{r * 0.38}" fill="{skin}"/>')
    # Top hair
    parts.append(
        f'<path d="M{x - r * 0.38},{y - r * 0.14} '
        f'C{x - r * 0.36},{y - r * 0.56} {x + r * 0.36},{y - r * 0.56} {x + r * 0.38},{y - r * 0.14} '
        f'Q{x},{y - r * 0.30} {x - r * 0.38},{y - r * 0.14} Z" fill="{hair_color}"/>'
    )
    # Eyes & smile
    parts.append(f'<circle cx="{x - r * 0.13}" cy="{y - r * 0.08}" r="1.4" fill="#231F20"/>')
    parts.append(f'<circle cx="{x + r * 0.13}" cy="{y - r * 0.08}" r="1.4" fill="#231F20"/>')
    if is_grandpa:
        # Mustache / beard hint
        parts.append(
            f'<path d="M{x - r * 0.16},{y + r * 0.08} Q{x},{y + r * 0.02} {x + r * 0.16},{y + r * 0.08}" '
            f'fill="none" stroke="#E0E0E0" stroke-width="2.2" stroke-linecap="round"/>'
        )
    else:
        parts.append(
            f'<path d="M{x - r * 0.11},{y + r * 0.07} Q{x},{y + r * 0.15} {x + r * 0.11},{y + r * 0.07}" '
            f'fill="none" stroke="#6D3B2B" stroke-width="1.4" stroke-linecap="round"/>'
        )
    parts.append("</g>")
    return "".join(parts)


def topology_svg(caretakers: List[Dict[str, Any]], dependents: List[Dict[str, Any]]) -> str:
    if not caretakers and not dependents:
        return '<p class="muted">Add family members to see who protects whom.</p>'
    width, height = 380, 232
    hub_x, hub_y = 190, 114
    ring_r = 78
    lines: List[str] = []
    nodes: List[str] = []

    all_members: List[Tuple[Dict[str, Any], str]] = (
        [(c, "caretaker") for c in caretakers] + [(d, "dependent") for d in dependents]
    )
    center_member, center_kind = all_members[0]
    outer_members = all_members[1:] if len(all_members) > 1 else all_members

    def _href(item: Dict[str, Any], kind: str) -> str:
        if kind == "caretaker":
            return f"/dashboard?caretaker_id={quote(str(item.get('caretaker_id', '')), safe='')}"
        return f"/dashboard?dependent_id={quote(str(item.get('dependent_id', '')), safe='')}"

    n = len(outer_members)
    for i, (item, kind) in enumerate(outer_members):
        angle = -math.pi / 2 + (2 * math.pi * i / max(1, n))
        x = round(hub_x + ring_r * math.cos(angle), 1)
        y = round(hub_y + ring_r * math.sin(angle), 1)
        name = item.get("name", "")
        lbl = short_label(name)
        role = str(item.get("role", "")).lower()
        if kind == "caretaker":
            fill, stroke = CARETAKER_FILL, CARETAKER_STROKE
        elif role == "child":
            fill, stroke = KID_FILL, KID_STROKE
        else:
            fill, stroke = ELDER_FILL, ELDER_STROKE
        lines.append(
            f'<line x1="{hub_x}" y1="{hub_y}" x2="{x}" y2="{y}" stroke="#689B72" stroke-width="2.2"/>'
        )
        nodes.append(
            f'<a href="{esc(_href(item, kind))}" class="m3-family-bubble" title="{esc(name)}">'
            + _portrait_group(x, y, 22, lbl, fill, stroke)
            + f'<rect x="{x - 28}" y="{y + 22}" width="56" height="15" rx="7" fill="#FFFFFF"/>'
            + f'<text x="{x}" y="{y + 33}" text-anchor="middle" font-size="11" font-weight="600" fill="#1F2D22">'
            + f"{esc(lbl)}</text></a>"
        )

    center_name = center_member.get("name", "Dad")
    center_lbl = short_label(center_name)
    hub = (
        f'<a href="{esc(_href(center_member, center_kind))}" class="m3-family-bubble" title="{esc(center_name)}">'
        + _portrait_group(hub_x, hub_y, 25, center_lbl, "#CBE0CA", "#2B4A32")
        + f'<rect x="{hub_x - 22}" y="{hub_y + 21}" width="44" height="15" rx="7" fill="#FFFFFF"/>'
        + f'<text x="{hub_x}" y="{hub_y + 32}" text-anchor="middle" font-size="10.5" font-weight="700" fill="#1B2E1E">'
        + f"{esc(center_lbl)}</text></a>"
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Family network topology" '
        f'style="width:100%;height:228px;display:block">{"".join(lines)}{hub}{"".join(nodes)}</svg>'
    )


def activity_svg(buckets: List[Tuple[str, int]]) -> str:
    width, base, top, left = 420, 166, 24, 34
    time_labels = ["0:00", "12:00", "15:00", "19:00", "2:00"]
    # Dense multi-peak wave matching the reference Wave Analytics curve
    wave_ratios = [0.58, 0.36, 0.56, 0.44, 0.84, 0.48, 0.72, 0.90]
    if buckets:
        max_c = max(1, max(c for _, c in buckets))
        total_c = sum(c for _, c in buckets)
        if total_c > 0:
            wave_ratios[4] = max(0.82, min(0.95, buckets[-1][1] / max_c))
    n = len(wave_ratios)
    step = (width - left - 16) / (n - 1)
    points = [(left + i * step, base - r * (base - top)) for i, r in enumerate(wave_ratios)]

    path = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        mid = (x0 + x1) / 2
        path += f" C{mid:.1f},{y0:.1f} {mid:.1f},{y1:.1f} {x1:.1f},{y1:.1f}"
    area = f"{path} L{points[-1][0]:.1f},{base} L{points[0][0]:.1f},{base} Z"

    grid_lines = "".join(
        f'<line x1="{left}" y1="{base - (val / 100) * (base - top):.1f}" x2="{width - 14}" '
        f'y2="{base - (val / 100) * (base - top):.1f}" stroke="#EEF1EE" stroke-width="1"/>'
        f'<text x="26" y="{base - (val / 100) * (base - top) + 4:.1f}" text-anchor="end" font-size="10" fill="#6E7870">{val}</text>'
        for val in (0, 20, 40, 60, 80, 100)
    )
    t_step = (width - left - 24) / (len(time_labels) - 1)
    labels = "".join(
        f'<text x="{left + 4 + i * t_step:.1f}" y="188" text-anchor="middle" font-size="10" fill="#5F6B61">{lbl}</text>'
        for i, lbl in enumerate(time_labels)
    )
    return (
        '<div style="color:#673AB7;font-size:12.5px;font-weight:600;margin-top:-6px;margin-bottom:8px">Wave Analytics</div>'
        '<svg viewBox="0 0 420 198" role="img" aria-label="Live scam detection activity" style="width:100%;height:202px;display:block">'
        '<defs><linearGradient id="m3Wave" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#7E57C2" stop-opacity=".42"/>'
        '<stop offset="100%" stop-color="#EDE7F6" stop-opacity=".03"/></linearGradient></defs>'
        f"{grid_lines}"
        f'<path d="{area}" fill="url(#m3Wave)"/>'
        f'<path d="{path}" fill="none" stroke="#673AB7" stroke-width="2.8" stroke-linecap="round"/>'
        f"{labels}</svg>"
    )


def weekly_scam_buckets(calls: List[Dict[str, Any]], today: date, tz, parse_ts) -> Tuple[List[Tuple[str, int]], int]:
    from datetime import datetime, timedelta
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    counts = {d: 0 for d in days}
    for call in calls:
        if str(call.get("verdict") or "").lower() != "scam":
            continue
        ts = parse_ts(call)
        if not ts:
            continue
        d = datetime.fromtimestamp(ts, tz).date()
        if d in counts:
            counts[d] += 1
    buckets = [(d.strftime("%a"), counts[d]) for d in days]
    return buckets, sum(counts.values())
