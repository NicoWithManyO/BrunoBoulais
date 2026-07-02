# Brief pour Claude prod (ClauDevOp) — activer les paiements Stripe

## État actuel

Le code Stripe est **déjà déployé** (via `brunoboulais-deploy.sh`) :

- `apps/boutique/stripe_checkout.py` : création d'une **Checkout Session**
  hébergée (redirection plein écran vers checkout.stripe.com). Mode `payment`,
  devise EUR, `line_items` reconstruits depuis les snapshots de la commande.
- `apps/boutique/views.py::webhook_stripe` : **source de vérité** du paiement.
  `@csrf_exempt @require_POST`, vérifie la signature (`STRIPE_WEBHOOK_SECRET`)
  puis, sur `checkout.session.completed` payé, bascule la commande en « payé »
  de façon **atomique + idempotente** (un rejeu ne re-notifie pas).
- Réglages proxy déjà en place (`SECURE_PROXY_SSL_HEADER`,
  `USE_X_FORWARDED_HOST = True` dans `settings/prod.py`) : les `success_url` /
  `cancel_url` renvoyées à Stripe sont construites avec le **domaine public**,
  pas le Host interne.

**Ce qui manque** : les 3 secrets Stripe dans l'environnement prod. Tant qu'ils
sont vides, la création de session échoue (log « échec de création de la session
Stripe ») et le webhook rejette tout en 400.

Variables lues par Django (`brunoboulais/settings/base.py`) :

```
STRIPE_PUBLISHABLE_KEY
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
```

---

## ═══ ÉTAPE 1 — POSER LES 3 SECRETS DANS LE .env PROD ═══

Bruno te fournit les 3 valeurs (voir `to-bruno-stripe.md`). Elles vont dans le
fichier d'environnement chargé par le service systemd `brunoboulais`.

```bash
# Localiser le .env / EnvironmentFile réellement utilisé par le service
systemctl cat brunoboulais | grep -iE "EnvironmentFile|WorkingDirectory"

# Éditer ce .env (adapter le chemin) et renseigner les 3 lignes :
#   STRIPE_PUBLISHABLE_KEY=pk_...
#   STRIPE_SECRET_KEY=sk_...
#   STRIPE_WEBHOOK_SECRET=whsec_...

# Recharger le service pour prendre le nouvel environnement
sudo systemctl restart brunoboulais
```

- ⚠️ **Test vs Live** : en attendant l'activation du compte (SIREN), ce sont des
  clés `…_test_…`. Au passage Live, Bruno refournit des clés `…_live_…` → même
  procédure (les 3 en même temps, sinon signature webhook incohérente).
- Ne **jamais** committer ces valeurs. Le `.env` est hors Git.

---

## ═══ ÉTAPE 2 — RENDRE LE WEBHOOK JOIGNABLE DE L'EXTÉRIEUR ═══

Stripe appelle `POST https://jacques-bertin.manyo.dev/boutique/webhook/stripe/`.
La requête arrive **via Cloudflare** puis nginx → gunicorn.

Points de vigilance :

1. **nginx** : `/boutique/webhook/stripe/` doit être routé vers gunicorn comme le
   reste du site (aucun `location` ne doit l'exclure). Payload Stripe petit, pas
   de souci de `client_max_body_size`.
2. **Cloudflare — ne PAS challenger cet endpoint.** WAF / Bot Fight Mode /
   « Under Attack » renverraient un 403 ou un JS-challenge à Stripe → paiements
   jamais confirmés. Recommandé : CF → Security → WAF → **exception (Skip)** sur
   `URI Path equals /boutique/webhook/stripe/` (skip Bot Fight Mode + Managed
   Rules).
3. **Authenticated Origin Pulls** (si activé, cf `to-prod.md` étape 3) : OK tant
   que le domaine reste **proxifié par Cloudflare** (orange cloud) — c'est CF qui
   présente le cert client à l'origine. Vérifier que le DNS de
   `jacques-bertin.manyo.dev` est bien en **proxy CF**, pas en DNS-only.
4. **Rate-limit** : ne pas appliquer de rate-limit agressif (nginx ou appli) sur
   cet endpoint — Stripe rejoue en cas d'échec, plusieurs fois sur ~3 jours.

---

## ═══ ÉTAPE 3 — VÉRIFICATION ═══

```bash
# 1. Les 3 secrets sont bien dans l'environnement du process
sudo systemctl show brunoboulais -p Environment | tr ' ' '\n' | grep -c STRIPE_
# Attendu : 3  (ou vérifier directement l'EnvironmentFile)

# 2. Depuis l'extérieur, l'endpoint est actif.
#    400 = signature Stripe absente → rejet : c'est NORMAL et ATTENDU,
#    ça prouve que la requête atteint Django et que le webhook répond.
curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST https://jacques-bertin.manyo.dev/boutique/webhook/stripe/
# Attendu : 400
# Un 403 / 503 / page de challenge = problème Cloudflare ou nginx (cf étape 2).
```

Test fonctionnel complet (fait par Bruno) : commande de test carte `4242…` →
dans le dashboard Stripe → Webhooks, l'événement `checkout.session.completed`
doit afficher une réponse **200**. Si Stripe signale un échec de livraison,
regarder les logs :

```bash
sudo journalctl -u brunoboulais --since "10 min ago" | grep -iE "boutique|stripe|webhook"
```

---

## ═══ « ET AUTRE ÉVENTUELLEMENT » — CHECKLIST SECRETS/PROD ═══

Pendant que tu es dans le `.env` prod, vérifier ces variables (impact direct
boutique) :

- **`BREVO_API_KEY`** — **critique** : c'est ce qui envoie le **mail de récap de
  commande** à Bruno. Si vide, toute commande (CB payée comme chèque/virement)
  part **sans notif** → `notified=False`, à traiter à la main. À vérifier en
  priorité.
- **`DEFAULT_FROM_EMAIL` / `CONTACT_EMAIL`** : expéditeur / destinataire des
  notifs (actuellement `boulaisbruno@free.fr`).
- **`ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`** : doivent contenir
  `jacques-bertin.manyo.dev` (nécessaire pour le retour depuis Stripe).
- `SENTRY_DSN`, `MONDIAL_RELAY_BRAND` : optionnels, ne bloquent pas les
  paiements.

---

## Contraintes (identiques à `to-prod.md`)

- **Ne jamais modifier les `*.py`** côté serveur : le code se change côté dev
  local + `git pull` via `brunoboulais-deploy.sh`.
- Secrets **hors Git** (dans le `.env` / drop-in systemd), jamais dans un commit.
- Privilégier les commandes **idempotentes** et les drop-ins systemd.
- Si tu touches une conf nginx ou Cloudflare, **consigne le diff** dans un
  fichier texte à côté de ton rapport pour que Bruno garde l'historique.
