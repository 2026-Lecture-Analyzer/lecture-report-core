"""원문 하이라이트 인터랙티브 컴포넌트(공용) — 항목 리스트(좌) + 원문 형광펜(우).

dashboard.py 의 _highlight_component 를 부작용 없는 모듈로 분리해 여러 대시보드가 공유.
hover: 근거 하이라이트 + 자동스크롤 · click: 고정(pin).
"""
from __future__ import annotations

import html
import json

from src.analyze.checklist import CATEGORIES
from src.report.highlight_html import resolve_chunk_ids

_CAT_COLORS = {"C1": "#6366f1", "C2": "#0ea5e9", "C3": "#10b981", "C4": "#f59e0b", "C5": "#ec4899"}
_SCORE_COLOR = {5: "#059669", 4: "#34d399", 3: "#f59e0b", 2: "#f97316", 1: "#ef4444"}
_WEIGHT_LABEL = {"high": "높음", "mid": "중간", "low": "낮음", "높음": "높음", "중간": "중간", "낮음": "낮음"}
_EVAL_BADGE = {
    "metric": ("지표", "#3b82f6"), "local": ("검색", "#f59e0b"),
    "global": ("전역", "#ec4899"), "positional": ("위치", "#10b981"),
}


def _item_color(score):
    return _SCORE_COLOR.get(score, "#94a3b8")


def _fmt_metric(metric):
    if not metric:
        return ""
    name = metric.get("name", "")
    value = metric.get("value")
    _label = {
        "filler_rate": ("필러율", lambda v: f"{v:.1%}"),
        "pace_cpm": ("속도", lambda v: f"{v:.0f}cpm"),
        "honorific_ratio": ("존댓말비율", lambda v: f"{v:.0%}"),
        "incomplete_ratio_utt": ("미완결율", lambda v: f"{v:.0%}"),
        "incomplete_ratio": ("미완결율", lambda v: f"{v:.0%}"),
    }
    label, fmt = _label.get(name, (name, str))
    try:
        val_str = fmt(value) if value is not None else "?"
    except Exception:
        val_str = str(value)
    parts = [f"{label} {val_str}"]
    if metric.get("top_filler"):
        parts.append(f"최다 '{metric['top_filler']}'")
    if metric.get("n") is not None:
        parts.append(f"{metric['n']}회")
    return " · ".join(parts)


def render_highlight(items_data: list[dict], chunks: list[dict], height: int = 600) -> None:
    """항목 리스트(좌) + 원문 형광펜 하이라이트(우) 인터랙티브 뷰를 Streamlit 에 렌더."""
    resolve_chunk_ids(items_data, chunks)
    chunk_map = {c["chunk_id"]: html.escape(c["clean_text"]) for c in chunks}
    chunk_ids_ordered = [c["chunk_id"] for c in chunks]
    chunk_times = {
        c["chunk_id"]: f"{c.get('start_time', '')}–{c.get('end_time', '')}"
        for c in chunks if c.get("start_time")
    }

    by_cat = {c: [] for c in sorted(CATEGORIES)}
    for item in items_data:
        by_cat.setdefault(item["category"], []).append(item)

    items_html_parts = []
    for cat_key in sorted(CATEGORIES):
        items_in_cat = by_cat.get(cat_key, [])
        if not items_in_cat:
            continue
        dot_color = _CAT_COLORS.get(cat_key, "#94a3b8")
        items_html_parts.append(f"""
        <div class="cat-header">
          <span class="cat-dot" style="background:{dot_color}"></span>
          <span>{cat_key} · {CATEGORIES[cat_key]}</span>
        </div>""")
        for item in items_in_cat:
            score = item.get("score")
            color = _item_color(score)
            weight = _WEIGHT_LABEL.get(item.get("weight", ""), "")
            verdict = html.escape((item.get("verdict") or "")[:100])
            title = html.escape(item.get("title", ""))
            evidence = item.get("evidence", [])
            quotes_json = json.dumps([e.get("quote", "") for e in evidence], ensure_ascii=False)
            chunk_ids_json = json.dumps([e.get("chunk_id", -1) for e in evidence])
            score_disp = str(score) if score is not None else "N/A"
            badge_label, badge_color = _EVAL_BADGE.get(item.get("eval_type", ""), ("", "#94a3b8"))
            badge_html = (f'<span class="eval-badge" style="background:{badge_color}20;'
                          f'color:{badge_color};border:1px solid {badge_color}40">{badge_label}</span>'
                          ) if badge_label else ""
            metric_text = html.escape(_fmt_metric(item.get("metric")))
            metric_html = f'<span class="metric-val">{metric_text}</span>' if metric_text else ""
            items_html_parts.append(f"""
        <div class="item-row"
             data-quotes='{html.escape(quotes_json, quote=True)}'
             data-chunk-ids='{chunk_ids_json}'
             onmouseenter="onHover(this)" onmouseleave="onLeave(this)" onclick="onClick(this)">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <span class="item-title">{title}</span>
            <span class="item-score" style="color:{color}">{score_disp}점</span>
          </div>
          <div style="display:flex;align-items:center;gap:5px;margin-top:3px;flex-wrap:wrap">
            <span class="item-weight">{weight}</span>
            {badge_html}
            {f'<span class="item-verdict">{verdict}</span>' if verdict else ''}
          </div>
          {f'<div style="margin-top:2px">{metric_html}</div>' if metric_html else ''}
        </div>""")

    items_html = "\n".join(items_html_parts)
    chunk_times_json = json.dumps(chunk_times, ensure_ascii=False)
    chunks_html = "\n".join(
        f'<p class="chunk" id="chunk-{cid}" data-cid="{cid}"'
        f' data-orig="{html.escape(chunk_map.get(cid, ""), quote=True)}">{chunk_map.get(cid, "")}</p>'
        for cid in chunk_ids_ordered)
    chunk_map_json = json.dumps(chunk_map, ensure_ascii=False)

    raw_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1e293b; background: white; }}
  .container {{ display: flex; height: {height}px; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }}
  .items-panel {{ width: 36%; min-width: 220px; overflow-y: auto; background: #f8fafc; border-right: 1px solid #e2e8f0; padding: 10px 8px; flex-shrink: 0; }}
  .panel-label {{ font-size: 11px; font-weight: 600; color: #94a3b8; letter-spacing: .05em; text-transform: uppercase; padding: 0 4px 8px; border-bottom: 1px solid #e2e8f0; margin-bottom: 6px; }}
  .cat-header {{ display: flex; align-items: center; gap: 5px; font-size: 10.5px; font-weight: 700; color: #64748b; letter-spacing: .04em; text-transform: uppercase; padding: 10px 8px 4px; margin-top: 2px; }}
  .cat-dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }}
  .item-row {{ padding: 8px 10px; border-radius: 8px; margin-bottom: 3px; cursor: pointer; border: 1px solid transparent; transition: background .12s, border-color .12s, box-shadow .12s; user-select: none; }}
  .item-row:hover, .item-row.active {{ background: white; border-color: #c7d2fe; box-shadow: 0 1px 6px rgba(99,102,241,.12); }}
  .item-row.pinned {{ background: #eff6ff; border-color: #6366f1; box-shadow: 0 1px 8px rgba(99,102,241,.22); }}
  .item-title {{ font-size: 12.5px; font-weight: 600; color: #1e293b; flex: 1; margin-right: 6px; }}
  .item-weight {{ font-size: 10px; color: #94a3b8; background: #e2e8f0; border-radius: 4px; padding: 1px 5px; white-space: nowrap; flex-shrink: 0; }}
  .item-score {{ font-size: 13px; font-weight: 700; white-space: nowrap; flex-shrink: 0; }}
  .item-verdict {{ font-size: 11px; color: #64748b; line-height: 1.4; }}
  .eval-badge {{ font-size: 9.5px; font-weight: 700; border-radius: 4px; padding: 1px 5px; white-space: nowrap; flex-shrink: 0; letter-spacing: .02em; }}
  .metric-val {{ font-size: 10.5px; color: #3b82f6; background: #eff6ff; border-radius: 4px; padding: 1px 6px; white-space: nowrap; }}
  .text-panel {{ flex: 1; overflow-y: auto; padding: 14px 20px; background: white; }}
  .text-header {{ font-size: 11px; font-weight: 600; color: #94a3b8; letter-spacing: .05em; text-transform: uppercase; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px; margin-bottom: 14px; }}
  .chunk {{ font-size: 13.5px; line-height: 1.85; color: #374151; margin-bottom: 18px; padding-bottom: 18px; border-bottom: 1px solid #f8fafc; transition: opacity .2s; }}
  .chunk.dimmed {{ opacity: .2; }} .chunk.active {{ opacity: 1; }}
  mark.hl {{ background: #fef08a; border-radius: 3px; padding: 1px 1px; box-decoration-break: clone; -webkit-box-decoration-break: clone; }}
  ::-webkit-scrollbar {{ width: 5px; }} ::-webkit-scrollbar-track {{ background: transparent; }} ::-webkit-scrollbar-thumb {{ background: #e2e8f0; border-radius: 4px; }}
</style></head><body>
<div class="container">
  <div class="items-panel"><div class="panel-label">평가 항목 &nbsp;· hover / click 고정</div>{items_html}</div>
  <div class="text-panel"><div class="text-header" id="text-header">강의 원문</div><div id="text-content">{chunks_html}</div></div>
</div>
<script>
const chunkMap = {chunk_map_json};
const chunkTimes = {chunk_times_json};
let currentRow = null, pinnedRow = null, leaveTimer = null;
function escRe(s) {{ return s.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&'); }}
function hlFrag(out, frag) {{ frag = frag.trim(); if (frag.length < 4) return out;
  try {{ return out.replace(new RegExp('(' + escRe(frag) + ')', 'g'), '<mark class="hl">$1</mark>'); }} catch(e) {{ return out; }} }}
function applyHighlights(text, quotes) {{ let out = text;
  quotes.forEach(q => {{ if (!q) return;
    let frag = q.replace(/\\s*[.…]+\\s*$/, '').trim(); if (frag.length < 4) return;
    if (text.includes(frag)) {{ out = hlFrag(out, frag); return; }}
    let s = frag; while (s.length >= 8 && !text.includes(s)) {{ const i = s.lastIndexOf(' '); if (i < 0) {{ s = ''; break; }} s = s.slice(0, i); }}
    if (s.length >= 8) out = hlFrag(out, s); }});
  return out; }}
function resetChunks() {{ document.querySelectorAll('.chunk').forEach(el => {{ const cid = parseInt(el.dataset.cid);
    el.innerHTML = chunkMap[cid] ?? el.dataset.orig ?? ''; el.classList.remove('dimmed', 'active'); }});
  document.getElementById('text-header').textContent = '강의 원문'; }}
function applyRowHighlight(row) {{ const quotes = JSON.parse(row.dataset.quotes || '[]');
  const chunkIds = JSON.parse(row.dataset.chunkIds || '[]'); const relevant = new Set(chunkIds);
  resetChunks(); if (quotes.length === 0) return; let scrolled = false;
  document.querySelectorAll('.chunk').forEach(el => {{ const cid = parseInt(el.dataset.cid);
    if (!relevant.has(cid)) {{ el.classList.add('dimmed'); }}
    else {{ el.classList.add('active'); el.innerHTML = applyHighlights(chunkMap[cid] ?? '', quotes);
      if (!scrolled) {{ el.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }}); scrolled = true; }} }} }});
  const timeStr = chunkIds.length > 0 && chunkTimes[chunkIds[0]] ? ' &nbsp;·&nbsp; ' + chunkTimes[chunkIds[0]] : '';
  document.getElementById('text-header').innerHTML = '근거 청크 ' + chunkIds.join(', ') + ' &nbsp;·&nbsp; 인용 ' + quotes.length + '건' + timeStr; }}
function onHover(row) {{ if (pinnedRow && pinnedRow !== row) return; clearTimeout(leaveTimer);
  if (currentRow && currentRow !== row) currentRow.classList.remove('active'); currentRow = row; row.classList.add('active'); applyRowHighlight(row); }}
function onLeave(row) {{ if (pinnedRow === row) return; leaveTimer = setTimeout(() => {{ if (currentRow === row) {{ row.classList.remove('active'); currentRow = null; resetChunks(); }} }}, 400); }}
function onClick(row) {{ if (pinnedRow === row) {{ pinnedRow = null; row.classList.remove('pinned'); }}
  else {{ if (pinnedRow) pinnedRow.classList.remove('pinned'); pinnedRow = row; row.classList.add('pinned'); clearTimeout(leaveTimer);
    if (currentRow && currentRow !== row) currentRow.classList.remove('active'); currentRow = row; row.classList.add('active'); applyRowHighlight(row); }} }}
</script></body></html>"""

    import streamlit.components.v1 as components
    components.html(raw_html, height=height + 4, scrolling=False)
