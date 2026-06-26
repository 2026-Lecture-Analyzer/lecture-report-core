"""골든셋 vs 파이프라인 예측 MAE 계산.

사용법:
    # 박채린 only
    python -m scripts.run_mae_eval

    # 찬희 only
    python -m scripts.run_mae_eval \
        --gold ~/Downloads/gold \
        --pred ~/Downloads/analysis.jsonl

    # 합산 (두 골드셋 + 두 pred)
    python -m scripts.run_mae_eval \
        --gold ~/Downloads/files/2026-02-23_27_kdt-backendj-21th_gold_ALL.jsonl \
        --gold ~/Downloads/gold \
        --pred outputs/gold_eval/analysis.jsonl \
        --pred ~/Downloads/analysis.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

# 박채린 gold 축약형 → analysis item_key 매핑
_KEY_MAP = {
    "C3_code":       "C3_code_explanation",
    "C3_connection": "C3_concept_connection",
    "C3_term":       "C3_term_explanation",
}

CATEGORIES = {
    "C1": "언어 품질",
    "C2": "강의 구조",
    "C3": "개념 설명",
    "C4": "진행 방식",
    "C5": "실습 및 적용",
}


def _gold_key(d: dict) -> str:
    """gold 레코드에서 매칭 키 추출. lecture_id가 있으면 세션 포함, 없으면 날짜만."""
    if "lecture_id" in d:
        return d["lecture_id"]          # "2026-02-09_오전"
    return d.get("source", "")[:10]     # "2026-02-23"


def load_gold(paths: list[Path]) -> dict[str, dict[str, int]]:
    """여러 gold 파일/폴더 → {lecture_id_or_date: {item_key: score}}"""
    gold: dict[str, dict[str, int]] = defaultdict(dict)

    def _load_file(p: Path) -> None:
        with p.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                key = _gold_key(d)
                item_id = _KEY_MAP.get(d["item_id"], d["item_id"])
                gold[key][item_id] = d["score"]

    for path in paths:
        if path.is_dir():
            for jsonl in sorted(path.rglob("*.jsonl")):
                _load_file(jsonl)
        else:
            _load_file(path)

    return dict(gold)


def load_pred(paths: list[Path]) -> dict[str, dict[str, float]]:
    """여러 analysis.jsonl → {key: {item_key: avg_score}}.

    key는 세션("2026-02-09_오전")과 날짜("2026-02-23") 두 형태 모두 포함.
    날짜 키는 해당 날짜의 세션 평균값.
    """
    sess_acc: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for path in paths:
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                lid = d.get("lecture_id", "")
                key = lid if ("_오전" in lid or "_오후" in lid) else (d.get("date") or lid[:10])
                if isinstance(d.get("score"), int):
                    sess_acc[key][d["item_key"]].append(d["score"])

    # 세션별 평균
    by_sess = {k: {ik: sum(v)/len(v) for ik, v in items.items()}
               for k, items in sess_acc.items()}

    # 날짜별 평균 (오전+오후 합산) — 날짜 키가 이미 없는 경우에만 추가
    date_acc: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for key, items in by_sess.items():
        date = key[:10]
        for ik, v in items.items():
            date_acc[date][ik].append(v)

    result = dict(by_sess)
    for date, items in date_acc.items():
        result[date] = {ik: sum(v)/len(v) for ik, v in items.items()}

    return result


def mae_stats(gold: dict[str, int], pred: dict[str, float]) -> dict:
    errs, signed, within1 = [], [], 0
    for k, g in gold.items():
        p = pred.get(k)
        if p is None:
            continue
        errs.append(abs(p - g))
        signed.append(p - g)
        if abs(p - g) <= 1:
            within1 += 1
    n = len(errs) or 1
    return {"mae": round(sum(errs) / n, 3),
            "bias": round(sum(signed) / n, 3),
            "within1": within1,
            "n": len(errs)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, action="append", dest="golds",
                    default=None, metavar="PATH",
                    help="gold JSONL 파일 또는 폴더 (반복 가능)")
    ap.add_argument("--pred", type=Path, action="append", dest="preds",
                    default=None, metavar="PATH",
                    help="analysis.jsonl 파일 (반복 가능)")
    args = ap.parse_args()

    golds = args.golds or [Path.home() / "Downloads/files/2026-02-23_27_kdt-backendj-21th_gold_ALL.jsonl"]
    preds = args.preds or [Path("outputs/gold_eval/analysis.jsonl")]

    gold_all = load_gold(golds)
    pred_all = load_pred(preds)

    keys = sorted(set(gold_all) & set(pred_all))
    if not keys:
        print("⚠️  겹치는 데이터 없음")
        print("  gold 키:", sorted(gold_all)[:10])
        print("  pred 키:", sorted(pred_all)[:10])
        return

    print("=" * 70)
    print(f"{'강의':18} {'MAE↓':>6} {'±1이내':>8} {'편향':>7} {'항목수':>6}")
    print("-" * 70)
    all_errs, all_signed, all_within1, all_n = [], [], 0, 0
    cat_errs: dict[str, list] = defaultdict(list)

    for key in keys:
        g = gold_all[key]
        p = pred_all[key]
        s = mae_stats(g, p)
        print(f"{key:18} {s['mae']:>6.2f}   {s['within1']}/{s['n']} ({100*s['within1']//s['n']}%)  "
              f"{s['bias']:>+6.2f}  {s['n']:>4}")
        for k, gv in g.items():
            pv = p.get(k)
            if pv is not None:
                cat = k.split("_")[0]
                err = abs(pv - gv)
                cat_errs[cat].append(err)
                all_errs.append(err)
                all_signed.append(pv - gv)
                if err <= 1:
                    all_within1 += 1
                all_n += 1

    print("=" * 70)
    n = len(all_errs) or 1
    print(f"{'전체 평균':18} {sum(all_errs)/n:>6.2f}   {all_within1}/{all_n} "
          f"({100*all_within1//all_n}%)  {sum(all_signed)/n:>+6.2f}  {all_n:>4}")
    print()

    print("[카테고리별 MAE]")
    for cat, name in CATEGORIES.items():
        errs = cat_errs.get(cat, [])
        if errs:
            print(f"  {cat} {name:10} MAE={sum(errs)/len(errs):.2f}  ({len(errs)}항목·{len(keys)}세션)")
    print("=" * 70)

    print("\n[항목별 오차 (전체 세션 평균)]")
    item_errs: dict[str, list] = defaultdict(list)
    for key in keys:
        for k, gv in gold_all[key].items():
            pv = pred_all[key].get(k)
            if pv is not None:
                item_errs[k].append(abs(pv - gv))

    for k in sorted(item_errs):
        errs = item_errs[k]
        mae = sum(errs) / len(errs)
        bar = "█" * int(mae * 4)
        print(f"  {k:28} {mae:.2f} {bar}")


if __name__ == "__main__":
    main()
