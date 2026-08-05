#!/usr/bin/env python3
"""
rescore_existing.py — Re-score les fiches déjà promues dans appels/*.yml avec
le scoring courant (score_opportunity.score_fiche).

Contexte (2026-08-02) : deux changements viennent d'être apportés à
score_opportunity.py (barème criteres.yml branché + bug de fuite du bonus
profil interne corrigé ; filtre discipline resserré, leçon L8/L9). Les fiches
déjà publiées avant ces changements ont un `score` et un `criteres_programme`
calculés avec l'ancien code — cet écart ne se corrige jamais tout seul (les
fiches déjà promues ne repassent pas dans watch.py). Ce script réconcilie.

Portée volontairement limitée à appels/ (les fiches ACTIVES) :
- archive/ est exclu. Ces fiches sont expirées par construction
  (date_limite < aujourd'hui) — leur repasser dans hard_filters() renverrait
  systématiquement "date_limite passée" et écraserait à tort leur score
  historique, qui documente leur pertinence AU MOMENT où elles étaient
  ouvertes (cf. INSTRUCTION-DEMARRAGE.md §11 "Archivage des expirées").

Deux issues possibles par fiche :
  - hard_filter_pass=True  → score + criteres_programme + _interne_affinite
    mis à jour en place.
  - hard_filter_pass=False pour une raison AUTRE que "date_limite passée"
    (discipline incompatible, type non reconnu, fee sans dotation) → la
    fiche n'aurait plus dû être promue avec les règles actuelles. Déplacée
    vers discovery/quarantine/{type}/ (jamais supprimée, cf. convention leçon
    L1), avec la raison consignée dans _meta.quarantine_reason.
  - hard_filter_pass=False pour "date_limite passée" → IGNORÉE (relève de
    deadline_tracker.py, pas de ce script).

Écrit un rapport JSON dans reports/rescore_<date>.json.

GARDE-FOU (ajouté 2026-08-05, suite à un incident réel) : le tout premier run
de ce script (2026-08-02, déclenché en CI car l'auth Claude locale était
expirée en session Cowork) a silencieusement échoué sur TOUS ses appels
Claude — auth invalide côté CI ce jour-là aussi — et a donc écrasé les 53
fiches traitées avec le score de repli neutre (4/10, criteres_programme tout
"inconnu") au lieu d'un vrai score. Rien dans le script ne détectait cet échec
systémique : hard_filters() ne dépend pas de Claude (les 15 mises en
quarantaine ce jour-là étaient correctes), mais score_fiche() avale les
exceptions Claude et retourne des valeurs de repli sans distinction entre
"vraiment neutre" et "Claude a échoué". D'où le canary + circuit-breaker
ci-dessous : mieux vaut échouer bruyamment que corrompre silencieusement.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
APPELS_DIR = ROOT / "appels"
QUARANTINE_DIR = ROOT / "discovery" / "quarantine"
REPORTS_DIR = ROOT / "reports"
TYPES = ["residence", "bourse", "prix", "exposition"]

sys.path.insert(0, str(ROOT / "scripts"))
import score_opportunity

CANARY_PROMPT = 'Réponds uniquement par ce JSON, sans rien ajouter autour : {"ok": true}'

# Circuit-breaker : au-delà de ce taux d'échec (et d'un minimum d'appels pour
# que le taux soit significatif), on arrête le run plutôt que de continuer à
# écrire des scores de repli neutres sur les fiches restantes.
MAX_FAILURE_RATE = 0.5
MIN_CALLS_BEFORE_CHECK = 4  # 2 fiches (2 appels Claude chacune) — testé : en cas
# d'échec total, le canary bloque tout avant la première écriture ; ce seuil
# limite le nombre de fiches pouvant être écrasées à repli neutre si Claude
# tombe EN COURS de run (après un canary réussi) à ~2 fiches maximum.

_stats = {"ok": 0, "fail": 0}
_original_call_claude = score_opportunity._call_claude


def _tracked_call_claude(prompt: str) -> str:
    try:
        result = _original_call_claude(prompt)
        _stats["ok"] += 1
        return result
    except Exception:
        _stats["fail"] += 1
        raise


def _circuit_open() -> bool:
    total = _stats["ok"] + _stats["fail"]
    return total >= MIN_CALLS_BEFORE_CHECK and (_stats["fail"] / total) > MAX_FAILURE_RATE


def _canary_check() -> bool:
    """Un appel Claude réel avant de toucher le moindre fichier. Si Claude ne
    répond pas (auth expirée, CLI absent, etc.), on préfère échouer bruyamment
    ici plutôt que d'écrire 50+ scores de repli neutres — cf. incident du
    2026-08-02 documenté en tête de fichier."""
    try:
        raw = _original_call_claude(CANARY_PROMPT)
        return "true" in raw.lower()
    except Exception as e:
        print(f"CANARY ÉCHEC — Claude indisponible, run annulé sans rien écrire : {e}", file=sys.stderr)
        return False


def main():
    score_opportunity._call_claude = _tracked_call_claude

    if not _canary_check():
        print("rescore_existing : ABANDON — canary Claude en échec, aucune fiche modifiée.")
        sys.exit(1)

    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    today = _dt.date.today().isoformat()
    updated, quarantined, unchanged, errors = [], [], [], []
    circuit_tripped = False

    for type_id in TYPES:
        if circuit_tripped:
            break
        d = APPELS_DIR / type_id
        if not d.exists():
            continue
        for path in sorted(d.glob("*.yml")):
            if circuit_tripped:
                break
            try:
                fiche = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception as e:
                errors.append({"path": str(path), "error": f"load: {e}"})
                continue

            try:
                sc = score_opportunity.score_fiche(fiche)
            except Exception as e:
                errors.append({"path": str(path), "error": f"score: {e}"})
                continue

            if _circuit_open():
                # Le canary est passé mais le taux d'échec Claude grimpe en
                # cours de run (auth expirée en cours de route, rate limit...).
                # On s'arrête ici plutôt que de continuer à écrire des scores
                # de repli neutres sur le reste des fiches — cette fiche-ci
                # (déjà scorée, potentiellement en repli) N'EST PAS écrite.
                circuit_tripped = True
                errors.append({
                    "path": str(path),
                    "error": f"circuit-breaker déclenché (échecs Claude {_stats['fail']}/{_stats['ok']+_stats['fail']}) — run interrompu, fiches restantes non traitées",
                })
                break

            if not sc["hard_filter_pass"]:
                if sc["hard_filter_reason"] == "date_limite passée":
                    continue  # relève de deadline_tracker.py, pas ce script
                dest_dir = QUARANTINE_DIR / type_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                fiche.setdefault("_meta", {})["quarantine_reason"] = sc["hard_filter_reason"]
                fiche["_meta"]["quarantined_at"] = now
                fiche["_meta"]["quarantined_by"] = "rescore_existing.py (resserrement filtre discipline, leçon L8)"
                (dest_dir / path.name).write_text(
                    yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120),
                    encoding="utf-8",
                )
                path.unlink()
                quarantined.append({
                    "uid": fiche.get("uid"), "type": type_id,
                    "nom": (fiche.get("opportunite") or {}).get("nom"),
                    "raison": sc["hard_filter_reason"],
                })
                continue

            old_score = fiche.get("score")
            new_score = sc["score"]
            fiche["score"] = new_score
            fiche["criteres_programme"] = sc["criteres_programme"]
            fiche["_interne_affinite"] = {
                "match": sc["bonus_profil_interne"] > 0,
                "signaux": sc["signaux_profil_interne"],
                "bonus_score": sc["bonus_profil_interne"],
            }
            path.write_text(
                yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120),
                encoding="utf-8",
            )
            entry = {
                "uid": fiche.get("uid"), "type": type_id,
                "nom": (fiche.get("opportunite") or {}).get("nom"),
                "old_score": old_score, "new_score": new_score,
            }
            if old_score != new_score:
                updated.append(entry)
            else:
                unchanged.append(entry)

    report = {
        "date": today,
        "circuit_breaker_tripped": circuit_tripped,
        "claude_calls_ok": _stats["ok"], "claude_calls_fail": _stats["fail"],
        "n_updated": len(updated), "n_unchanged": len(unchanged),
        "n_quarantined": len(quarantined), "n_errors": len(errors),
        "updated": updated, "quarantined": quarantined, "errors": errors,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"rescore_{today}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"rescore_existing : {len(updated)} score(s) changé(s), "
          f"{len(unchanged)} inchangé(s), {len(quarantined)} mis en quarantaine, "
          f"{len(errors)} erreur(s). Rapport : {report_path.relative_to(ROOT)}")
    if circuit_tripped:
        print(f"⚠ CIRCUIT-BREAKER DÉCLENCHÉ ({_stats['fail']}/{_stats['ok']+_stats['fail']} échecs Claude) — "
              f"run interrompu avant la fin, relancer une fois Claude rétabli.")
        sys.exit(1)
    print("DONE")


if __name__ == "__main__":
    main()
