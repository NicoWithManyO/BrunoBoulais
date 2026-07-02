# Stripe — ce que TU dois faire (côté dashboard)

## Où on en est

- Le code de paiement CB est **déjà en prod** : le site redirige vers une page
  de paiement **hébergée par Stripe** (checkout.stripe.com), et un **webhook**
  Stripe est la **source de vérité** qui valide le paiement et fait passer la
  commande en « payé ».
- Il ne manque que **3 clés** à renseigner côté serveur pour que ça tourne.
- Rappel : la CB est **retirée temporairement** de la page paiement en attendant
  ton **SIREN** (chèque / virement en attendant). Tu peux quand même **tout
  préparer et tester en mode Test dès maintenant** ; le passage en mode Live se
  fera quand le compte sera activé.

---

## 1. Le compte Stripe

- Se connecter / créer le compte sur https://dashboard.stripe.com
- Pour encaisser **en vrai** (mode Live), Stripe demande d'**activer le compte** :
  identité + **SIREN/SIRET** + IBAN pour les versements. → à faire quand tu as
  le SIREN.
- En attendant : tout se teste en **mode Test** (interrupteur « Test mode » en
  haut à droite du dashboard).

---

## 2. Récupérer les clés d'API (2 clés)

Dashboard → **Développeurs → Clés API** (*Developers → API keys*)

- **Clé publiable** (`pk_test_…` en test, `pk_live_…` en live)
  → variable `STRIPE_PUBLISHABLE_KEY`
- **Clé secrète** (`sk_test_…` / `sk_live_…`)
  → variable `STRIPE_SECRET_KEY` — **secret, à ne jamais partager publiquement**

---

## 3. Créer le webhook (la 3ᵉ clé)

Dashboard → **Développeurs → Webhooks** → **Ajouter un endpoint**

- **URL de l'endpoint** :
  `https://jacques-bertin.manyo.dev/boutique/webhook/stripe/`
- **Événement à écouter** : cocher **uniquement** `checkout.session.completed`
- Valider, puis ouvrir l'endpoint créé et copier le **« Signing secret »**
  (`whsec_…`) → variable `STRIPE_WEBHOOK_SECRET`
- ⚠️ Le webhook du **mode Test** et celui du **mode Live** sont **séparés** :
  il faudra en créer un pour chaque, chacun avec son propre `whsec_…`.

---

## 4. Transmettre les 3 clés

Une fois les 3 valeurs en main :

```
STRIPE_PUBLISHABLE_KEY
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
```

→ les transmettre à **ClauDevOp** (voir `to-prod-paiements.md`) pour qu'il les
pose dans l'environnement du serveur.
**Ne pas les mettre dans le code ni dans un commit** — elles vivent dans le
`.env` du serveur, hors Git.

---

## 5. Tester (mode Test)

- Être en **mode Test** dans le dashboard **et** que le serveur utilise les clés
  `…_test_…`.
- Sur le site, passer une commande et payer avec la **carte de test** Stripe :
  `4242 4242 4242 4242`, date future quelconque, CVC quelconque, code postal
  quelconque.
- Vérifier :
  - la commande passe en **« Payé »** dans la gestion ;
  - tu reçois le **mail de récap** de commande ;
  - dans le dashboard Stripe → Webhooks → ton endpoint, l'événement
    `checkout.session.completed` apparaît avec une réponse **200**.

---

## 6. Passage en Live (quand le SIREN est validé)

1. Activer le compte (étape 1).
2. Basculer le dashboard en **mode Live**, récupérer les clés `pk_live_…` /
   `sk_live_…` (étape 2) et **recréer le webhook en Live** (étape 3) pour
   obtenir un `whsec_…` live.
3. Transmettre les 3 nouvelles valeurs « live » à ClauDevOp, qui remplacera les
   clés test dans le `.env`.
4. Refaire un test avec une vraie petite commande.

---

## Rappels sécurité

- Les clés `sk_…` et `whsec_…` sont des **secrets** : jamais dans un mail
  public, un commit, une capture partagée.
- En cas de fuite : dashboard → **Développeurs → Clés API → Rouler (roll)** la
  clé, puis mettre à jour le `.env` (via ClauDevOp).
