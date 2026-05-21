// ─────────────────────────────────────────────────────────────────────────────
// suggest-worker.js — Relais formulaire public → issue GitHub
// ─────────────────────────────────────────────────────────────────────────────
// Reçoit la soumission du formulaire « Suggérer une source » du site public,
// et crée une issue GitHub taguée `nouvelle-source` dans le repo de veille.
// Le script scripts/review_issues.py la traite ensuite automatiquement
// (probe de l'URL → ajout à discovery/candidates.yml).
//
// Le token GitHub n'est JAMAIS exposé au navigateur : il vit côté Worker,
// dans la variable d'environnement secrète GITHUB_TOKEN.
//
// Déploiement : voir worker/README.md
// ─────────────────────────────────────────────────────────────────────────────

const REPO = "CedricMabilotte/residence-veille";
const ALLOWED_ORIGIN = "https://residence.actitude.org";

export default {
  async fetch(request, env) {
    const cors = {
      "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    // Préflight CORS
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors });
    }
    if (request.method !== "POST") {
      return json({ ok: false, error: "Méthode non autorisée" }, 405, cors);
    }

    let data;
    try {
      data = await request.json();
    } catch {
      return json({ ok: false, error: "Corps de requête invalide" }, 400, cors);
    }

    // Honeypot anti-spam : champ caché qui doit rester vide.
    // Si rempli → bot ; on renvoie ok pour ne pas l'aider à itérer.
    if (data._gotcha) {
      return json({ ok: true }, 200, cors);
    }

    const url = String(data.url || "").trim();
    if (!/^https?:\/\/.+\..+/i.test(url)) {
      return json({ ok: false, error: "URL manquante ou invalide" }, 400, cors);
    }

    const type = String(data.type || "").trim().slice(0, 40);
    const note = String(data.note || "").trim().slice(0, 1000);

    let host = url;
    try {
      host = new URL(url).hostname;
    } catch {
      /* garde l'URL brute */
    }

    // Corps de l'issue au format attendu par review_issues.py
    // (lignes « **URL:** », « **Type:** », « **Justification:** »).
    const body = [
      "_Suggestion soumise via le formulaire public du site._",
      "",
      `**URL:** ${url}`,
      type ? `**Type:** ${type}` : "",
      note ? `**Justification:** ${note}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    const ghResp = await fetch(
      `https://api.github.com/repos/${REPO}/issues`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "residence-suggest-worker",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title: `Nouvelle source : ${host}`,
          body,
          labels: ["nouvelle-source"],
        }),
      }
    );

    if (!ghResp.ok) {
      // 422 = label inexistant le plus souvent (voir README §5).
      return json(
        { ok: false, error: `GitHub a refusé la création (${ghResp.status})` },
        502,
        cors
      );
    }

    return json({ ok: true }, 200, cors);
  },
};

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}
