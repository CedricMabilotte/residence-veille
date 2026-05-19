#!/usr/bin/env python3
"""Notifie Discord/Slack/Mastodon des docs scorés >= 9 d'un run."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCORE_MIN = 9


def format_message(doc: dict, platform: str) -> str:
    """Adapte le markdown/format au support cible."""
    title = doc.get("filename") or doc.get("url", "")
    src = doc.get("source", "")
    score = doc.get("score", 0)
    url = doc.get("url", "")
    raison = (doc.get("raison") or "")[:240]
    if platform == "slack":
        # Slack mrkdwn : *gras*, <url|texte>
        return (f"*Nouvelle pépite ({score}/10)* — _{src}_\n"
                f"<{url}|{title}>\n> {raison}")
    if platform == "discord":
        # Discord markdown classique
        return (f"**Nouvelle pépite ({score}/10)** — *{src}*\n"
                f"[{title}]({url})\n> {raison}")
    if platform == "mastodon":
        # Texte brut, 500 caractères max
        body = f"Nouvelle fiche {score}/10 — {src}\n{title}\n{raison}\n{url}"
        return body[:480]
    return f"[{score}/10] {title} — {url}"


def _post_discord(url: str, content: str) -> tuple[bool, str]:
    """Webhook Discord : payload {content}."""
    try:
        import requests
    except ImportError:
        return False, "requests indisponible"
    try:
        r = requests.post(url, json={"content": content}, timeout=15)
        return r.status_code in (200, 204), f"http {r.status_code}"
    except Exception as e:
        return False, str(e)


def _post_slack(url: str, content: str) -> tuple[bool, str]:
    """Webhook Slack : payload {text}."""
    try:
        import requests
    except ImportError:
        return False, "requests indisponible"
    try:
        r = requests.post(url, json={"text": content}, timeout=15)
        return r.status_code == 200, f"http {r.status_code}"
    except Exception as e:
        return False, str(e)


def _post_mastodon(instance: str, token: str, status: str) -> tuple[bool, str]:
    """Toot Mastodon : POST /api/v1/statuses avec Bearer token."""
    try:
        import requests
    except ImportError:
        return False, "requests indisponible"
    try:
        r = requests.post(f"{instance.rstrip('/')}/api/v1/statuses",
                          headers={"Authorization": f"Bearer {token}"},
                          data={"status": status, "visibility": "public"},
                          timeout=15)
        return r.status_code in (200, 201), f"http {r.status_code}"
    except Exception as e:
        return False, str(e)


def notify_run(report_path: Path, webhook_urls: dict[str, str]) -> dict:
    """Pour chaque doc >= 9 dans le report, envoie les notifs configurées."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    results = report.get("results", [])
    candidates = [d for d in results if int(d.get("score", 0)) >= SCORE_MIN]
    sent = 0
    errors: list[str] = []
    dry_run = webhook_urls.get("__dry_run__") == "1"
    for doc in candidates:
        for platform in ("discord", "slack", "mastodon"):
            url = webhook_urls.get(platform)
            if not url:
                continue
            msg = format_message(doc, platform)
            if dry_run:
                print(f"--- {platform} (dry-run) ---\n{msg}\n")
                sent += 1
                continue
            if platform == "discord":
                ok, info = _post_discord(url, msg)
            elif platform == "slack":
                ok, info = _post_slack(url, msg)
            elif platform == "mastodon":
                token = webhook_urls.get("mastodon_token", "")
                ok, info = _post_mastodon(url, token, msg)
            else:
                ok, info = False, "unknown"
            if ok:
                sent += 1
            else:
                errors.append(f"{platform}/{doc.get('filename','?')}: {info}")
    return {"sent": sent, "errors": errors, "candidates": len(candidates)}


def _load_webhooks_from_env(dry_run: bool = False) -> dict[str, str]:
    """Construit le dict de config à partir des variables d'environnement."""
    cfg: dict[str, str] = {}
    if v := os.getenv("WEBHOOK_DISCORD"):
        cfg["discord"] = v
    if v := os.getenv("WEBHOOK_SLACK"):
        cfg["slack"] = v
    if v := os.getenv("MASTODON_INSTANCE"):
        cfg["mastodon"] = v
    if v := os.getenv("MASTODON_TOKEN"):
        cfg["mastodon_token"] = v
    if dry_run:
        cfg["__dry_run__"] = "1"
    return cfg


if __name__ == "__main__":
    # Validation : dry-run sur le dernier report.
    reports = sorted((ROOT / "reports").glob("run_*.json"))
    if not reports:
        print("[webhooks] aucun report trouvé", file=sys.stderr)
        sys.exit(1)
    latest = reports[-1]
    print(f"[webhooks] dry-run sur {latest.name}")
    # En dry-run on simule la présence des trois webhooks.
    cfg = _load_webhooks_from_env(dry_run=True)
    if not any(k in cfg for k in ("discord", "slack", "mastodon")):
        cfg.update({
            "discord": "https://discord.com/api/webhooks/FAKE",
            "slack": "https://hooks.slack.com/services/FAKE",
            "mastodon": "https://mamot.fr",
            "mastodon_token": "FAKE",
            "__dry_run__": "1",
        })
    summary = notify_run(latest, cfg)
    print(f"[webhooks] récap: {summary}")
