# API TTL-LAMa v1

Ce guide décrit les blueprints `api_v1`, `admin` et `user_api`. Les routes
de l'interface web et le blueprint distinct `global_config` ne sont pas inclus.

## Avant de commencer

- Toutes les routes ci-dessous commencent par `/api/v1`.
- Utilisez HTTPS et envoyez les corps de requête en JSON avec
  `Content-Type: application/json`.
- Un identifiant utilisateur est un UUID. Les identifiants de profil,
  d'équipement et de bail sont des entiers positifs.
- Un profil décrit un accès réseau ; il ne donne pas les droits
  d'administration. Les routes `/admin` exigent un compte actif avec
  `is_admin: true`.
- Les dates sont des chaînes ISO 8601 en UTC. Les listes sont des tableaux
  JSON, y compris lorsqu'elles sont vides.

## Authentification interne

En mode d'authentification interne, commencez par demander un jeton CSRF,
puis conservez le cookie de session associé pour envoyer les identifiants.
Exemple avec `curl` et `jq` :

```sh
API="https://ttl-lama.example/api/v1"
CSRF=$(curl -sS -c cookies.txt "$API/csrf" | jq -r '.csrf_token')

curl -sS -b cookies.txt -H "X-CSRFToken: $CSRF" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"MOT_DE_PASSE"}' \
  "$API/auth"
```

La réponse `200` contient :

```json
{
  "user": {"id": "UUID", "username": "admin", "email": null, "is_admin": true},
  "access_token": "JETON_DE_SESSION",
  "token_type": "Bearer"
}
```

Pour les requêtes suivantes, transmettez `Authorization: Bearer
JETON_DE_SESSION`. Le jeton est sensible : ne l'inscrivez pas dans les logs,
le code source ou une URL. Les exemples suivants supposent que `TOKEN` contient
un jeton administrateur valide. Remplacez les valeurs d'exemple avant usage.

Une requête avec un cookie d'authentification, ou sans Bearer, doit fournir
`X-CSRFToken` pour les méthodes qui modifient des données. Le cookie obtenu
avec `/csrf` doit accompagner la requête ; un jeton Bearer non vide dispense du
contrôle CSRF, mais doit être valide pour accéder à une route protégée. Si
`Authorization` est présent, il est prioritaire sur le cookie. Les trois
routes OIDC ci-dessous sont exemptées du contrôle CSRF.

## Exemple : créer un utilisateur et lui attribuer un profil

1. Connectez-vous avec un compte administrateur comme indiqué ci-dessus.
2. Créez l'utilisateur :

   ```sh
   curl -sS -X POST "$API/admin/users" \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"username":"alice","email":"alice@example.org","password":"MOT_DE_PASSE"}'
   ```

   La réponse `201` contient l'objet utilisateur, dont `id`. Sans `password`,
   en mode interne, elle contient à la place `user` et `generated_password`.
   Le mot de passe généré n'est communiqué qu'à cette création : transmettez-le
   à l'utilisateur par un canal sûr.
3. Choisissez un profil existant avec `GET /admin/profiles`, puis attribuez-le :

   ```sh
   curl -sS -X PUT \
     -H "Authorization: Bearer $TOKEN" \
     "$API/admin/users/UUID_UTILISATEUR/profiles/ID_PROFIL"
   ```

   La réponse `200` est l'objet d'attribution. L'opération est idempotente.
4. L'utilisateur se connecte avec ses propres identifiants. Il peut consulter
   ses profils dans `GET /users/me/overview`, créer un équipement, puis demander
   un bail avec son propre jeton :

   ```sh
   curl -sS -X POST "$API/users/me/devices" \
     -H "Authorization: Bearer $USER_TOKEN" -H 'Content-Type: application/json' \
     -d '{"name":"portable","public_key":"CLE_PUBLIQUE_WIREGUARD"}'

   curl -sS -X POST "$API/users/me/leases" \
     -H "Authorization: Bearer $USER_TOKEN" -H 'Content-Type: application/json' \
     -d '{"device_id":1,"profile_id":1,"duration":"1h"}'
   ```

   Remplacez les identifiants par ceux retournés par l'API. Générez la paire
   de clés WireGuard sur le poste client : seule la clé publique est envoyée.
   La création du bail renvoie `201` après confirmation de son application VPN.
   Récupérez ensuite `GET /users/me/leases/ID_BAIL/configuration` et complétez
   localement le modèle avec la clé privée, sans la transmettre au serveur.

## Routes d'authentification et de compte

Les chemins du tableau sont relatifs à `/api/v1`.

| Méthode | Route | Requête et réponse |
| --- | --- | --- |
| GET | `/csrf` | Retourne `200` et `{"csrf_token":"..."}`. Conserver le cookie associé. |
| POST | `/auth` | Mode interne : `{"username":"...","password":"..."}` ; retourne le compte et `access_token`. |
| POST | `/auth/oidc/exchange` | `{"ticket":"..."}` ; échange un ticket CLI à usage unique contre `access_token` et `token_type`. |
| POST | `/auth/oidc/device` | Démarre l'autorisation OIDC de type appareil. |
| POST | `/auth/oidc/device/poll` | `{"device_code":"..."}` ; consulte l'état de l'autorisation. |
| POST | `/auth/logout` | Révoque uniquement la session courante ; réponse `204`. |
| GET | `/users/me` | Retourne `user` et `sessions`, tableau de `{"expires_at":"..."}` pour les sessions actives. |
| GET | `/users/me/overview` | Retourne `user`, `devices`, `leases` et `profiles` de l'utilisateur courant. |
| PATCH | `/users/me/password` | `{"current_password":"...","new_password":"..."}` ; réponse `204`. |

Le changement de mot de passe exige le mode interne et des chaînes de 1 à
1024 caractères. Il révoque toutes les sessions de l'utilisateur, y compris
la session courante. Une erreur de mot de passe actuel renvoie `401` ; une
authentification interne indisponible ou un identifiant interne absent renvoie
`409`. `/auth` renvoie `405` lorsque le mode interne n'est pas activé.

### OIDC pour une application cliente

Le fournisseur configuré doit prendre en charge Device Authorization.
`POST /auth/oidc/device` retourne `device_code`, `user_code`,
`verification_uri`, `expires_in` et `interval`, et éventuellement
`verification_uri_complete`. Affichez à l'utilisateur l'URI et le code
utilisateur ; gardez `device_code` confidentiel. Interrogez `/auth/oidc/device/poll`
en respectant `interval` et augmentez le délai en cas de `slow_down`.

La réponse de consultation contient `status` : `pending`, `slow_down`,
`denied`, `expired` ou `complete`. Seul `complete` contient aussi
`access_token` et `token_type: "Bearer"`. Les états `denied` et `expired`
terminent le parcours. L'indisponibilité du mode ou du service peut renvoyer
`501`, et une erreur du fournisseur `502`.

L'échange de ticket sert au parcours CLI avec navigateur : le ticket obtenu
après le retour d'authentification expire après deux minutes et ne peut être
échangé qu'une fois. L'échange retourne `400` si le ticket manque, `401` s'il
est invalide ou expiré. Les réponses OIDC ne sont pas mises en cache.

## Routes utilisateur

Ces routes, relatives à `/api/v1/users/me`, exigent un utilisateur actif et
ne donnent accès qu'à ses propres ressources. Les listes peuvent inclure des
ressources révoquées pour conserver l'historique.

| Méthode | Route | Résultat |
| --- | --- | --- |
| GET | `/devices` | Liste des équipements. |
| POST | `/devices` | Crée un équipement ; objet créé, `201`. |
| GET | `/devices/<device_id>` | Lit un équipement. |
| DELETE | `/devices/<device_id>` | Révoque l'équipement et ses baux ; `204`. |
| GET | `/leases` | Liste des baux. |
| POST | `/leases` | Crée et applique un bail ; objet créé, `201`. |
| GET | `/leases/<lease_id>` | Lit un bail. |
| GET | `/leases/<lease_id>/configuration` | Retourne les paramètres WireGuard d'un bail actif. |
| POST | `/leases/<lease_id>/revoke` | Révoque le bail ; objet actualisé, `200`. |

**Équipement à créer :** `name` est une chaîne de 1 à 255 caractères et
`public_key` une chaîne de 1 à 512 caractères. Les deux sont obligatoires.
La réponse contient `id`, `user_id`, `name`, `public_key`, `created_at` et
`revoked_at`. La clé publique doit correspondre à la clé privée conservée sur
le client.

**Bail à créer :** `device_id` et `profile_id` sont obligatoires ; `duration`
est facultatif. L'équipement doit être actif et appartenir à l'utilisateur ;
le profil doit être actif et lui être attribué. Sans durée, la durée par défaut
du profil est utilisée ; elle ne peut dépasser son maximum. La réponse contient
`id`, `user_id`, `device_id`, `profile_user_id`, `profile_id`, `created_at`,
`ended_at`, `revoked_at` et `status` : `active`, `expired` ou `revoked`.

La configuration contient `lease_id`, `interface`, `device_public_key`,
`server_public_key`, `endpoint`, `addresses`, `allowed_ips`,
`active_lease_ids`, `expires_at` et `configuration_template`. Ce dernier
contient le marqueur `REPLACE_WITH_LOCAL_PRIVATE_KEY`. Les réseaux et les
identifiants peuvent regrouper plusieurs baux actifs partageant le même pair
WireGuard. Une configuration indisponible ou un bail inactif renvoie `409`.

La création et la révocation d'un bail attendent la confirmation du backend.
En cas d'échec ou de délai dépassé, la réponse est `503` avec un `lease_id`
lorsqu'il est connu ; vérifiez l'état du bail avant de réessayer. Les règles
réseau nécessitent une configuration externe adaptée : WireGuard seul ne
garantit pas le filtrage des destinations par profil.

## Routes d'administration

Ces routes sont relatives à `/api/v1/admin` et exigent un administrateur actif.
Les lectures individuelles et les modifications renvoient un objet JSON, les
listes un tableau. Les suppressions sont logiques et conservent l'historique.

| Méthode | Route | Résultat ou filtres facultatifs |
| --- | --- | --- |
| GET | `/users` | Liste ; filtres `device`, `lease`, `profile`. |
| POST | `/users` | Crée un utilisateur ; `201`. |
| GET, PATCH, DELETE | `/users/<user_id>` | Lit, modifie ou désactive un utilisateur ; DELETE : `204`. |
| GET | `/users/<user_id>/profiles` | Liste ses profils attribués. |
| PUT | `/users/<user_id>/profiles/<profile_id>` | Attribue le profil ; objet d'attribution, `200`. |
| DELETE | `/users/<user_id>/profiles/<profile_id>` | Retire l'attribution et révoque ses baux ; `204`. |
| GET | `/devices` | Liste ; filtres `lease`, `profile`. |
| GET, PATCH, DELETE | `/devices/<device_id>` | Lit, modifie ou révoque un équipement ; DELETE : `204`. |
| POST | `/devices/<device_id>/block` | Bloque l'équipement et révoque ses baux ; objet actualisé, `200`. |
| GET | `/leases` | Liste ; filtres `user`, `device`, `profile`, `status`. |
| GET | `/leases/<lease_id>` | Lit un bail. |
| POST | `/leases/<lease_id>/revoke` | Révoque un bail ; objet actualisé, `200`. |
| GET | `/profiles` | Liste ; filtres `user`, `device`, `lease`. |
| POST | `/profiles` | Crée un profil ; `201`. |
| GET, PATCH, DELETE | `/profiles/<profile_id>` | Lit, modifie ou révoque un profil ; DELETE : `204`. |

Les filtres se combinent avec ET. Un filtre inconnu, invalide ou répété renvoie
`400`. Les filtres de relation avec les baux utilisent aussi l'historique ; les
relations utilisateur-profil ne concernent que les attributions actives.
`status` accepte `active`, `expired` ou `revoked`.

### Contrat utilisateur

Pour `POST /users`, `username` est obligatoire (1 à 50 caractères). Champs
facultatifs : `email` (1 à 254 caractères ou `null`), `enabled` (booléen,
défaut `true`), `is_admin` (booléen, défaut `false`), `password` (1 à 1024
caractères) et `oidc_links` (tableau d'objets `{"issuer":"...","subject":"..."}`).
Chaque chaîne OIDC contient de 1 à 255 caractères ; une même identité ne peut
être répétée. La gestion des mots de passe n'est disponible qu'en mode interne.
En mode externe, un mot de passe omis ne crée pas d'identifiant interne.

`PATCH /users/<user_id>` accepte ces champs sauf `oidc_links`, remplacé par
`link_oidc` et `unlink_oidc` de même format. Une identité ne peut figurer dans
les deux tableaux. La réponse utilisateur contient `id`, `username`, `email`,
`enabled`, `is_admin`, `created_at` et `last_login`, jamais le mot de passe.
Une attribution contient `id`, `user_id`, `profile_id`, `created_at` et
`revoked_at`.

### Contrat profil

Exemple de création ; `lease_target` doit désigner une interface du backend
configuré :

```json
{
  "name": "acces-interne",
  "default_duration": "1h",
  "maximum_duration": "8h",
  "lease_target": "wg0",
  "networks": ["10.0.0.0/24"],
  "address_pools": ["10.250.0.0/24"],
  "endpoint": "vpn.example.org:51820",
  "public_key": "CLE_PUBLIQUE_DU_SERVEUR"
}
```

Tous ces champs sont obligatoires à la création. Les durées positives utilisent
les unités `d`, `h`, `m`, `s`, combinables comme `1h30m` ; la durée par défaut
ne peut dépasser le maximum. `networks` contient au moins un CIDR de destination ;
`address_pools` contient au moins un CIDR d'adresses clientes, avec au plus un
réseau par famille IP. `endpoint` est de la forme `hote:port` ou `[IPv6]:port`.

La réponse contient `id`, `name`, `created_at`, `revoked_at` et `policy`.
`policy` contient les champs de l'exemple sauf `name` ; il peut être `null`
pour un ancien profil sans politique. `PATCH` accepte un sous-ensemble des
champs de création et valide la politique complète après fusion.

### Contrat équipement

`PATCH /devices/<device_id>` accepte `name` et/ou `public_key`, avec les mêmes
limites que pour la création utilisateur. Changer la clé publique révoque les
baux concernés. L'API administrateur ne crée pas d'équipement : utilisez la
route utilisateur correspondante.

### Effets des révocations

Désactiver un utilisateur révoque ses sessions, équipements, attributions et
baux. Réactiver le compte ne restaure pas ces accès. Révoquer un profil révoque
ses attributions et baux ; modifier sa politique révoque les baux concernés.
Le changement de mot de passe ou de privilège invalide les sessions concernées.
Le retrait effectif du réseau dépend du traitement par le backend.

## Erreurs et règles communes

| Code | Signification courante |
| --- | --- |
| 400 | Corps, filtre ou jeton CSRF invalide ou absent. |
| 401 | Authentification absente, invalide ou expirée. |
| 403 | Compte authentifié sans privilèges administrateur. |
| 404 | Ressource introuvable ou non accessible à l'utilisateur. |
| 409 | Conflit d'unicité ou d'état. |
| 500 | Erreur interne, notamment de base de données. |
| 503 | Opération VPN non confirmée ou indisponible. |

Les erreurs des routes utilisateur et administrateur sont généralement des
objets `{"error":"..."}` ; certaines erreurs de validation ajoutent `details`.
Ne supposez pas que toutes les erreurs, notamment CSRF, ont un corps JSON.
Les corps de ces routes rejettent les champs inconnus, les types incorrects et
les modifications vides. `null` est rejeté sauf pour `email`. Les identifiants,
dates et relations gérés par le serveur ne peuvent pas être modifiés.

Les réponses administrateur, utilisateur et d'authentification sensibles portent
`Cache-Control: no-store`. L'affectation et la révocation d'un bail sont
idempotentes ; les opérations de suppression conservent l'historique.
