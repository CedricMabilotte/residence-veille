#!/usr/bin/env python3
"""
dedup.py — Détection de doublons de PDFs par SHA-256 du contenu.

Maintient un registre `synopsis/duplicates.json` :
{
  "by_hash": { "<sha256>": ["doc_id_1", "doc_id_2", ...], ... },
  "by_doc":  { "doc_id_1": "<sha256>", ... },
  "meta":    { "last_update": "...", "total_pdfs": N, "duplicate_clusters": K }
}

Permet :
- d'enregistrer un nouveau PDF et de savoir s'il duplique un existant,
- de récupérer les grappes de doublons,
- de produire un rapport statistique (économie d'espace potentielle).

Pure Python (hashlib, json). Aucune dépendance externe.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# Chemin par défaut du registre
_DEFAULT_REGISTRY = Path(__file__).parent.parent / "synopsis" / "duplicates.json"

# Taille du buffer de lecture (64 Kio : bon compromis débit/RAM)
_CHUNK = 64 * 1024


def compute_hash(pdf_path: Path) -> str:
    """SHA-256 du contenu binaire du fichier. Lève FileNotFoundError si absent."""
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def compute_text_fingerprint(pdf_path: Path,
                              max_pages: int = 30,
                              min_word_len: int = 5,
                              max_tokens: int = 2000) -> list[str] | None:
    """Extrait un 'bag of words' du PDF — set ordonné de mots représentatifs.

    Détecte les vrais doublons (même contenu, mise en page différente) au-delà
    des différences d'ordre d'extraction : 'foo-cahier.pdf' (livret imposé) vs
    'foo-pageparpage.pdf' (une page par feuille) ont les mêmes mots mais dans
    un ordre différent à l'extraction.

    Retourne une liste triée de tokens uniques (mots ≥ min_word_len chars).
    Comparaison ultérieure par Jaccard.
    Retourne None si PyMuPDF indisponible ou extraction ratée.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    try:
        doc = fitz.open(pdf_path)
        chunks = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            chunks.append(page.get_text("text") or "")
        doc.close()
        text = "\n".join(chunks)
    except Exception:
        return None

    import re
    text = text.lower()
    # Tokens : suites de caractères alphanumériques unicode
    tokens = re.findall(r"\w+", text, flags=re.UNICODE)
    # Filtrer : longueur min + uniques + triés
    unique = sorted(set(t for t in tokens if len(t) >= min_word_len))
    if not unique:
        return None
    return unique[:max_tokens]


def jaccard(a: list[str] | set[str], b: list[str] | set[str]) -> float:
    """Similarité de Jaccard entre deux ensembles de tokens."""
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# Seuil par défaut pour considérer 2 PDFs comme doublons textuels
DUP_JACCARD_THRESHOLD = 0.85


def _load_registry(registry_path: Path) -> dict:
    """Charge le registre ou retourne une structure vierge."""
    if registry_path.exists():
        try:
            return json.loads(registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ! registre corrompu, repart de zéro : {registry_path}")
    return {"by_hash": {}, "by_doc": {}, "meta": {}}


def _save_registry(registry: dict, registry_path: Path) -> None:
    """Recalcule meta puis écrit le JSON (atomique : tmp + replace)."""
    by_hash = registry.get("by_hash", {})
    by_doc = registry.get("by_doc", {})
    clusters = sum(1 for ids in by_hash.values() if len(ids) > 1)
    registry["meta"] = {
        "last_update": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_pdfs": len(by_doc),
        "duplicate_clusters": clusters,
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = registry_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(registry_path)


def register_pdf(pdf_path: Path, doc_id: str,
                 catalog_path: Path | None = None) -> dict:
    """Calcule le hash binaire ET le fingerprint texte, signale les doublons.

    Un doublon est détecté si l'un des deux empreintes correspond à un autre
    doc déjà enregistré : binaire identique (mêmes octets) OU texte identique
    (même contenu textuel, mise en page différente).
    """
    if catalog_path is not None:
        registry_path = catalog_path.parent / "duplicates.json"
    else:
        registry_path = _DEFAULT_REGISTRY

    registry = _load_registry(registry_path)
    # Migration douce : ajouter le bag-of-words registry si absent
    registry.setdefault("by_tokens", {})  # doc_id → list[str]

    sha = compute_hash(pdf_path)
    tokens = compute_text_fingerprint(pdf_path)

    # 1. Doublon binaire exact (toujours prioritaire)
    bucket_bin = registry["by_hash"].setdefault(sha, [])
    is_new_bin = doc_id not in bucket_bin
    duplicate_of = None
    duplicate_kind = None
    duplicate_similarity = None
    if bucket_bin and bucket_bin[0] != doc_id:
        duplicate_of = bucket_bin[0]
        duplicate_kind = "binary"
        duplicate_similarity = 1.0

    # 2. Doublon textuel (Jaccard contre les docs déjà connus)
    if tokens and not duplicate_of:
        best_id, best_sim = None, 0.0
        for other_id, other_tokens in registry["by_tokens"].items():
            if other_id == doc_id:
                continue
            sim = jaccard(tokens, other_tokens)
            if sim > best_sim:
                best_sim = sim
                best_id = other_id
        if best_sim >= DUP_JACCARD_THRESHOLD:
            duplicate_of = best_id
            duplicate_kind = "text"
            duplicate_similarity = round(best_sim, 3)

    if is_new_bin:
        bucket_bin.append(doc_id)
    if tokens:
        registry["by_tokens"][doc_id] = tokens
    registry["by_doc"][doc_id] = {"hash": sha, "n_tokens": len(tokens) if tokens else 0}
    _save_registry(registry, registry_path)

    return {
        "is_new":               is_new_bin and duplicate_of is None,
        "duplicate_of":         duplicate_of,
        "duplicate_kind":       duplicate_kind,  # "binary" | "text" | None
        "duplicate_similarity": duplicate_similarity,
        "hash":                 sha,
        "n_tokens":             len(tokens) if tokens else 0,
    }


def find_clusters(synopsis_path: Path) -> list[list[str]]:
    """Retourne la liste des grappes de doc_ids partageant le même hash (>1)."""
    registry_path = (synopsis_path
                     if synopsis_path.name == "duplicates.json"
                     else synopsis_path.parent / "duplicates.json")
    registry = _load_registry(registry_path)
    return [sorted(ids) for ids in registry["by_hash"].values() if len(ids) > 1]


def report(registry_path: Path = _DEFAULT_REGISTRY,
           pdf_dir: Path | None = None) -> dict:
    """Statistiques globales : total, uniques, doublons, espace gagné (Mo)."""
    registry = _load_registry(registry_path)
    by_hash = registry["by_hash"]
    total = sum(len(ids) for ids in by_hash.values())
    uniques = len(by_hash)
    duplicates = total - uniques

    # Espace potentiellement récupérable : taille (hash → 1er doc_id présent)
    saved_bytes = 0
    if pdf_dir is not None:
        for sha, ids in by_hash.items():
            if len(ids) <= 1:
                continue
            sample = next((p for p in pdf_dir.glob(f"{ids[0]}*.pdf")), None)
            if sample is not None and sample.exists():
                # Chaque doublon supplémentaire = taille gagnée
                saved_bytes += sample.stat().st_size * (len(ids) - 1)

    return {
        "total_pdfs": total,
        "unique_hashes": uniques,
        "duplicate_count": duplicates,
        "duplicate_clusters": sum(1 for ids in by_hash.values() if len(ids) > 1),
        "saved_bytes_estimate": saved_bytes,
        "saved_mb_estimate": round(saved_bytes / (1024 * 1024), 2),
    }


# ── Validation CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = Path(__file__).parent.parent
    docs_dir = root / "docs"
    covers_dir = root / "interface" / "covers"
    registry_path = root / "synopsis" / "duplicates.json"

    print(f"Scan de {docs_dir} ...")
    count = 0
    for pdf in sorted(docs_dir.glob("*.pdf")):
        # doc_id = préfixe avant le premier "_" (cf. convention du projet)
        doc_id = pdf.stem.split("_", 1)[0]
        res = register_pdf(pdf, doc_id, catalog_path=registry_path)
        count += 1
        if res["duplicate_of"]:
            print(f"  ⚠ {doc_id} duplique {res['duplicate_of']} (sha={res['hash'][:10]}…)")
    print(f"→ {count} PDF(s) traité(s)")

    # On scanne aussi les couvertures, pour la démo (PNG ⇒ SHA distinct)
    if covers_dir.exists():
        cov_count = sum(1 for _ in covers_dir.glob("*.png"))
        print(f"  (couvertures présentes : {cov_count} PNG — non incluses)")

    stats = report(registry_path=registry_path, pdf_dir=docs_dir)
    clusters = find_clusters(registry_path)
    print("\n── Rapport ──")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if clusters:
        print(f"\n  Grappes de doublons ({len(clusters)}) :")
        for c in clusters[:5]:
            print(f"    {c}")
