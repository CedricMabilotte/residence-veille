#!/usr/bin/env python3
"""claude_guard.py — circuit breaker pour la limite de session Claude Code CLI.

Incident du 2026-08-26 : quand le CLI Claude Code (authentifié via
CLAUDE_CODE_OAUTH_TOKEN, session d'abonnement Claude Pro/Max — pas une clé
API à l'usage) atteint sa limite de session, CHAQUE appel `claude -p ...`
échoue instantanément avec un message du type :
    "You've hit your session limit · resets 8:30pm (UTC)"
Sans détection dédiée, les scripts de veille (watch.py et consorts) retentent
cet appel pour chaque item restant, en boucle, pendant des heures — c'est ce
qui a bloqué le run veille-documentaire du 26/08 pendant 6h jusqu'à ce que
GitHub Actions le tue de force (timeout par défaut du job).

Usage dans un _call_claude() :
    import claude_guard
    def _call_claude(prompt, timeout=...):
        claude_guard.guard_before_call()          # <- avant le subprocess.run
        result = subprocess.run([...])
        if result.returncode != 0:
            claude_guard.check_result(result.stdout, result.stderr)  # <- avant le raise générique
            raise RuntimeError(f"claude exit {result.returncode} — stdout={result.stdout[:200]} stderr={result.stderr[:200]}")
        ...

Le flag est un état de module (donc partagé par tous les imports de
claude_guard dans le MÊME process `python scripts/watch.py`) : une fois
déclenché, tout appel _call_claude() ultérieur lève immédiatement
ClaudeSessionLimitError sans spawn de subprocess — le run continue donc sa
boucle sur les items restants en quelques secondes au lieu de plusieurs
heures, avec dégradation propre (les fonctions appelantes retombent déjà sur
leurs fallback existants en cas d'exception).
"""
from __future__ import annotations
import re

_session_limit_hit = False
_session_limit_message = ""

class ClaudeSessionLimitError(RuntimeError):
    """Le CLI Claude Code a signalé une limite de session/usage atteinte."""

_SESSION_LIMIT_RE = re.compile(
    r"session limit|usage limit|hit your.*limit", re.IGNORECASE
)

def session_limit_active() -> bool:
    return _session_limit_hit

def session_limit_message() -> str:
    return _session_limit_message

def _trip(msg: str) -> None:
    global _session_limit_hit, _session_limit_message
    if not _session_limit_hit:
        print(f"🛑 Limite de session Claude détectée — bascule en mode dégradé "
              f"pour le reste de ce run (plus d'appels Claude tentés) : {msg[:200]}")
    _session_limit_hit = True
    _session_limit_message = msg[:300]

def guard_before_call() -> None:
    """À appeler en tout début de _call_claude(), avant subprocess.run()."""
    if _session_limit_hit:
        raise ClaudeSessionLimitError(
            f"circuit breaker déjà déclenché pour ce run : {_session_limit_message}"
        )

def check_result(stdout: str = "", stderr: str = "") -> None:
    """À appeler quand result.returncode != 0, avant de lever une RuntimeError
    générique. Arme le breaker et lève ClaudeSessionLimitError si le message
    correspond à une limite de session/usage."""
    combined = f"{stdout or ''}\n{stderr or ''}"
    if _SESSION_LIMIT_RE.search(combined):
        _trip(combined.strip())
        raise ClaudeSessionLimitError(combined.strip()[:300])
