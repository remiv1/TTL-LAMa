# TODO TTL-LAMa

Cette liste décline la feuille de route de [docs/project.fr.md](docs/project.fr.md) en actions réalisables. Elle sert de suivi du travail, sans remplacer les décisions d’architecture.

Chaque grande ligne regroupe un chantier, chaque sous-tâche un résultat à obtenir et les cases à cocher les actions concrètes. Une case reste décochée tant que l’action n’a pas été vérifiée dans le code, la documentation ou les tests.

## 0. Qualifier l’état actuel

### 0.1 Établir le point de départ

- [x] Lancer la suite de tests existante et noter les éventuels échecs initiaux.
- [x] Vérifier les fonctionnalités présentes dans `src/auth/` et leurs tests, notamment les modes interne et OIDC.
- [x] Recenser les implémentations présentes pour la configuration, la persistance, les profils, les appareils, les baux, le provisionnement et l’audit.
- [x] Pour chaque sous-tâche ci-dessous, noter si elle est absente, partielle ou déjà réalisée, puis ajuster la liste sans supprimer les travaux utiles.

## 1. Finaliser la conception

### 1.1 Définir le modèle de menace

- [x] Lister les actifs à protéger : identifiants, sessions, clés publiques, configuration, baux et accès réseau.
  - [x] Transformer les identifiants utilisateurs en UUID.
  - [x] Données sensibles identifiées :
    - identifiant & mot de passe
    - clés publiques
    - liens vers les fournisseurs d'identité
    - sessions
    - appartenances à des groupes
  - [x] Créer une table de conservation des clés publiques et/ou privées.
  - [x] Créer une table pour la conservation des baux.
- [x] Décrire les acteurs, les frontières de confiance et les interfaces exposées.
- [x] Recenser les menaces liées à l’authentification, à l’autorisation, aux secrets, au conteneur et au backend réseau.
- [x] Associer à chaque menace une mesure de réduction et un risque résiduel accepté.
- [x] Vérifier que le modèle est cohérent avec [docs/security.fr.md](docs/security.fr.md).

### 1.2 Définir les concepts métier

- [x] Documenter les identifiants, attributs et états d’une identité, d’un appareil, d’un profil et d’un bail à partir des modèles et schémas réellement implémentés.
- [x] Décrire leurs relations, contraintes d’unicité et règles de propriété, en distinguant les données persistées des valeurs calculées ou dérivées.
- [x] Préciser les données qui ne doivent jamais être conservées, notamment les clés privées, mots de passe et jetons bruts.
- [x] Vérifier et documenter les cas d’usage principaux au regard du code et des tests : plusieurs appareils par identité, profils attribués et révocation d’un appareil ayant des baux actifs.
- [x] Mettre à jour les documents d’architecture français et anglais pour refléter le modèle vérifié.

### 1.3 Définir le cycle de vie des baux

- [x] Établir la liste minimale des états et les transitions autorisées.
- [x] Vérifier et documenter les conditions de création, d’activation après provisionnement, d’expiration, de révocation et d’échec, y compris les claims transitoires persistés et les états incertains du provisionnement.
- [x] Écrire les invariants : un bail expiré ou révoqué ne doit plus donner accès au réseau.
- [x] Vérifier la cohérence entre l’architecture, le fonctionnement opérationnel, le code et les tests; corriger notamment les descriptions de réconciliation au démarrage ou périodique.
- [x] Vérifier dans le code et les tests le comportement des transitions répétées et concurrentes, notamment révocation pendant l’application, expiration pendant la programmation et échec de suppression.
- [x] Vérifier les scénarios de redémarrage, de restauration des échéances et d’échec de provisionnement; compléter les tests uniquement si une lacune est confirmée.

### 1.4 Stabiliser la configuration

- [x] Décrire les paramètres de l’application, les profils d’accès et leurs valeurs par défaut.
- [x] Confirmer la priorité entre valeurs par défaut, YAML, variables d’environnement et fichiers de secrets.
- [x] Définir les validations des profils : réseaux autorisés, durée par défaut et durée maximale.
- [x] Vérifier les erreurs de configuration aux frontières de chargement : YAML invalide, secret absent ou illisible, et conflit entre valeur directe et paramètre `_FILE`; les erreurs de validation de schéma sont également couvertes par l’API.
- [x] Vérifier que les messages d’erreur, réponses API et journaux associés n’exposent aucune valeur de secret, y compris via les erreurs de validation et exceptions.
- [x] Fournir des exemples de configuration valides et invalides.

### 1.5 Définir les contrats des composants

- [x] Définir la frontière entre authentification, identité métier et autorisation.
- [x] Préciser les garanties transactionnelles nécessaires lors de la création ou de la révocation d’un bail.
- [x] Vérifier que les contrats ne dépendent pas de WireGuard ou d’un fournisseur d’identité précis.

### 1.6 Définir l’audit

- [x] Lister les événements à tracer avec leur résultat succès/échec, notamment les opérations de baux et de provisionnement, les expirations et les réconciliations.
- [x] Définir les métadonnées utiles au diagnostic et les identifiants métier à associer à l’événement, sans enregistrer de secret, jeton brut ni clé privée.
- [x] Définir le format des messages par origine : `[TTL-LAMa API]-[yyyy-mm-dd HH:mm:ss] : <operation>-<Log>` et `[TTL-LAMa Scheduler]-[yyyy-mm-dd HH:mm:ss] : <operation>-<Log>`, en UTC.
- [x] Définir la centralisation des journaux de l’API et du scheduler dans des fichiers historiques par niveau (`ERROR`, `WARNING`, `INFO`, `DEBUG`), ainsi que leur emplacement persistant, leur rotation, leur conservation et les droits d’accès.

## 2. Réaliser le prototype autonome

### 2.1 Valider le déploiement en conteneur

- [x] Générer un bundle d’installation sans écraser une sortie existante, avec les artefacts rangés selon les chemins du conteneur, les textes statiques issus de templates et les commandes Podman affichées sans exécution.
- [x] Confirmer l’exécution sans privilèges root et documenter les permissions requises.
- [x] Vérifier la persistance des données après arrêt et recréation réelle du conteneur avec le même volume `/data`.
- [x] Vérifier que les secrets sont montés séparément, exclus de l’image et absents des journaux.
- [x] Ajouter un contrôle de santé utilisable par le déploiement.
- [x] Documenter une procédure complète d’installation et de mise à jour, en mettant à jour `INSTALL.md` pour refléter l’installeur et le layout réellement généré.

### 2.2 Terminer l’authentification interne

- [x] Comparer les fonctions déjà présentes à la cible : création et gestion des comptes, sessions, protection CSRF et limitation des tentatives.
- [x] Décider et documenter le report de l’authentification multifacteur à la V2.
- [x] Définir et implémenter la limitation des tentatives de connexion : trois échecs consécutifs déclenchent un verrouillage temporaire de 15 minutes, configurable, avec tests et réponses génériques.
- [x] Tester les succès, refus, expirations de session, révocations et cas limites couverts par l’authentification actuelle.
- [x] Documenter la création du compte administrateur et la récupération du compte interne verrouillé par intervention directe de l’opérateur dans la base.

### 2.3 Mettre en place la persistance SQLite

- [x] Définir les tables et contraintes du modèle métier validé.
- [x] Implémenter les dépôts pour les identités, appareils, profils et baux; les événements d’audit sont conservés dans les journaux plutôt que dans un dépôt SQL.
- [x] Vérifier les transactions lors des opérations qui modifient à la fois un bail et son état de provisionnement.
- [x] Tester la création, la lecture, la mise à jour, la suppression et les transactions sur des bases temporaires.
- [x] Définir les migrations de schéma comme hors du périmètre de TTL-LAMa; l’opérateur applique les changements décrits dans le journal des modifications de chaque version.

### 2.4 Implémenter la gestion des appareils

- [x] Définir les opérations d’enregistrement, de consultation et de révocation d’un appareil.
- [x] Enregistrer les informations nécessaires à un appareil, dont la clé publique du client.
- [x] Vérifier qu’un utilisateur ne peut gérer que ses propres appareils.
- [x] Valider que les clés publiques sont non vides sans imposer un format WireGuard, et empêcher les doublons.
- [x] Tester les entrées invalides, les doublons et la révocation d’un appareil ayant un bail actif.

### 2.5 Implémenter les profils et les baux

- [x] Charger et valider les profils d’accès depuis la configuration déclarative.
- [x] Exposer uniquement à l’utilisateur les profils auxquels il est autorisé.
- [x] Créer un bail lié à une identité, un appareil et un profil, avec une expiration calculée côté serveur.
- [x] Refuser les durées hors limites et les réseaux fournis directement par l’utilisateur.
- [x] Permettre à l’utilisateur de consulter et révoquer ses propres baux.
- [x] Tester les autorisations, limites de durée et transitions principales du cycle de vie.
- [x] Tester le chargement des profils depuis le fichier configuré au démarrage de l’application.

### 2.6 Implémenter le backend WireGuard

- [x] Retenir une communication SSH du conteneur applicatif vers l’hôte VPN; ne pas confondre ce flux avec les commandes locales du CLI.
- Pour le MVP, utiliser une clé SSH dédiée plutôt que des certificats SSH; réévaluer les certificats si une CA est disponible.
- [x] Automatiser de façon idempotente la création d’un compte distant dédié non-root et l’application des permissions minimales.
- [x] Limiter sudo aux opérations WireGuard nécessaires; ne jamais accorder un accès sudo générique.
- [x] Générer et installer une clé SSH dédiée, épingler `known_hosts`, puis documenter la rotation et la révocation de la clé.
- [x] Monter la clé privée comme secret hors de l’image et configurer les paramètres SSH non secrets dans les fichiers de configuration.
- [x] Relier l’exécuteur SSH existant au backend serveur et au cycle de vie des baux.
- [x] Implémenter côté serveur l’ajout, la lecture et la suppression répétable d’un pair via l’hôte VPN.
- [x] Associer chaque pair provisionné à un appareil et à un bail.
- [x] Vérifier que les réseaux appliqués proviennent exclusivement du profil autorisé.
- [x] Valider côté serveur l’état et l’autorisation du bail avant toute opération privilégiée.
- [x] Tester les erreurs SSH et WireGuard, ainsi que l’absence de faux état actif après un échec.
- [x] Documenter et tester l’installation côté hôte : compte, permissions, sudoers, `known_hosts`, secrets et configuration WireGuard.

### 2.7 Garantir expiration, révocation et réconciliation

- [x] Programmer l’expiration des baux et la scrutation périodique des opérations en attente; la réconciliation complète est exécutée au démarrage seulement.
- [x] Déclencher l’expiration des baux arrivés à échéance.
- [x] Supprimer les accès associés aux baux expirés ou révoqués.
- [x] Au démarrage, comparer l’état désiré en base avec l’état WireGuard de l’hôte et restaurer les échéances.
- [x] Définir la résolution des divergences, y compris les pairs inconnus du serveur et les indisponibilités du backend.
- [x] Corriger les écarts sans créer de doublons et rendre les opérations répétables.
- [x] Tester la reprise par réconciliation après expiration ou état incertain, ainsi que les indisponibilités du backend.
- [x] Tracer les échecs et corrections dans les événements d’audit.

## 3. Intégrer des services externes

### 3.1 Terminer l’intégration OIDC

- [x] Vérifier le flux existant contre les exigences OIDC retenues et les contrôles de sécurité attendus.
- [x] Gérer les erreurs d’échange, d’état, de nonce, d’émetteur et de validation des jetons.
- [x] Définir la correspondance stable entre le sujet externe et l’identité locale.
- [x] Tester le flux avec un fournisseur simulé et documenter un exemple de configuration.

### 3.2 Ajouter les bases de données externes

- [x] Confirmer les moteurs réellement visés pour la première version intégrée.
- [x] Vérifier les ~~migrations~~, contraintes et types nécessaires sur chaque moteur retenu.
- [x] Ajouter des tests d’intégration isolés pour chaque moteur pris en charge.

### 3.3 Ajouter l’observabilité

- [x] Journaliser explicitement les succès et les échecs des opérations sensibles, dont l’application et la suppression d’un bail ainsi que les réconciliations.
- [x] Appliquer le format et la politique de niveaux définis en 1.6; centraliser les journaux de l’API et du scheduler dans des fichiers historiques séparés par niveau, avec rotation et conservation maîtrisées.
- [x] Vérifier par des tests et une revue des chemins d’erreur qu’aucun secret ou contenu de fichier secret n’apparaît dans les journaux.
- [x] Documenter les alertes utiles, notamment les échecs de réconciliation et de provisionnement.

> Pas de métriques exposées, hors scope.

## 4. Délier Interface et Profils

### 4.1 Contexte et décisions validées

Ce chantier permet à plusieurs profils utilisateurs de partager une même interface WireGuard tout en disposant de réseaux autorisés et de durées différents. Les sections précédentes décrivent le fonctionnement historique vérifié : leurs cases cochées ne prouvent pas que cette nouvelle architecture est déjà réalisée.

Les décisions suivantes ont été précisées avec l’utilisateur :

- Les profils sont l’entrée principale de la configuration. Chaque profil déclare son interface ; une interface peut être référencée par plusieurs profils. Ne pas conserver une liste d’interfaces qui génère implicitement un seul profil par interface.
- Un bail est rattaché à un seul profil. Un seul bail réservé ou actif est autorisé par utilisateur/appareil/profil. Plusieurs profils peuvent avoir des baux simultanés pour un même appareil sur une interface : conserver le pair jusqu’à la fin du dernier bail.
- `networks` contient les réseaux de destination auxquels le profil permet d’accéder, avec des CIDR IPv4 ou IPv6, notamment `/24`, `/32` ou `/128`. Il ne s’agit pas des adresses VPN attribuées au client.
- Les réseaux autorisés peuvent être identiques ou se chevaucher entre profils et utilisateurs. Un profil Administrateur doit pouvoir accéder aux mêmes destinations que des profils plus restreints, simultanément sur `wg0`.
- TTL-LAMa gère uniquement les baux et les pairs WireGuard. Le filtrage des destinations est une configuration externe sous la responsabilité de l’administrateur du routeur ; aucune opération nftables ne doit être réalisée par l’API, le scheduler ou le CLI des pairs.
- L’installeur détermine les règles nftables d’intégration, les affiche clairement sur stdout et propose leur inclusion dans le script de préparation de l’hôte. Il ne les applique jamais lui-même et n’exécute pas le script généré.
- Les `AllowedIPs` du client ne constituent pas une autorisation serveur. Sur un pair partagé, l’expiration partielle d’un profil ne garantit pas le retrait de ses destinations côté serveur ; une politique externe adaptée reste nécessaire. Aucun cumul dynamique de droits nftables n’est à implémenter.
- Ces réseaux doivent également être exposés au client via l’API et repris dans les `AllowedIPs` de sa configuration WireGuard. L’utilisateur doit pouvoir récupérer facilement le fichier de configuration depuis le navigateur, puis l’importer dans son client WireGuard.
- Aucune transition : ne prévoir ni migration des données existantes, ni compatibilité avec l’ancien format, ni conversion des anciens baux. Cette décision n’autorise pas une suppression automatique des données existantes.

Format retenu : les paramètres techniques sont répétés et validés comme cohérents pour une interface partagée. La plage cliente ci-dessous est illustrative et doit être adaptée au déploiement ; sa première adresse utilisable est réservée au routeur.

```yaml
backend:
  wireguard:
    profiles:
      - name: Administrateur
        interface: wg0
        endpoint: vpn.example.com:51820
        public_key: REPLACE_WITH_WIREGUARD_PUBLIC_KEY
        address_pools: [10.250.0.0/24]
        default_duration: 1h
        maximum_duration: 2h
        networks:
          - 10.100.0.0/24
          - 10.10.0.0/24
          - 10.20.0.0/24

      - name: Utilisateur fichiers
        interface: wg0
        endpoint: vpn.example.com:51820
        public_key: REPLACE_WITH_WIREGUARD_PUBLIC_KEY
        address_pools: [10.250.0.0/24]
        default_duration: 2h
        maximum_duration: 8h
        networks:
          - 10.20.0.0/24

      - name: Utilisateur Charlemagne
        interface: wg0
        endpoint: vpn.example.com:51820
        public_key: REPLACE_WITH_WIREGUARD_PUBLIC_KEY
        address_pools: [10.250.0.0/24]
        default_duration: 1h
        maximum_duration: 4h
        networks:
          - 10.10.0.0/24
```

### 4.2 État initial et cause du blocage

Constats avant implémentation, conservés pour expliquer le changement. Les résultats actuels sont suivis en 4.4 à 4.8.

- [src/api/config/c_profiles.py](src/api/config/c_profiles.py) : `WireGuardInterface` hérite actuellement de `AccessPolicy`. `BackendConfig.access_profiles` transforme chaque interface en profil, nommé d’après sa description ou son nom ; la validation interdit les interfaces dupliquées.
- [src/api/bootstrap.py](src/api/bootstrap.py) : charge cette configuration, importe les profils manquants et conserve les cibles autorisées dans `BACKEND_LEASE_TARGETS`.
- [src/api/common/db_objects/profile_policy.py](src/api/common/db_objects/profile_policy.py), [src/api/common/repositories/profiles.py](src/api/common/repositories/profiles.py) et [src/api/v1/admin/schemas.py](src/api/v1/admin/schemas.py) : les politiques persistées et l’API disposent déjà de `lease_target`, sans imposer une interface différente pour chaque profil. Le remplacement d’une politique révoque déjà les baux qui utilisaient l’ancienne.
- [src/api/common/repositories/leases.py](src/api/common/repositories/leases.py) : `_ensure_available` refuse les réseaux qui chevauchent les réservations existantes sur une même interface ; `create` copie `policy.networks` dans `LeaseProvisioning.document["addresses"]`. Cela empêche aussi plusieurs équipements d’utiliser simultanément un même profil.
- [cli/src/ttlama_cli/drivers/wireguard.py](cli/src/ttlama_cli/drivers/wireguard.py) : applique `addresses` avec `wg set <interface> peer <clé> allowed-ips ...`. Le contrat est défini dans [cli/src/ttlama_cli/drivers/_common.py](cli/src/ttlama_cli/drivers/_common.py) et lu par [cli/src/ttlama_cli/commands/backend/wireguard/peers.py](cli/src/ttlama_cli/commands/backend/wireguard/peers.py).
- [src/vpn_backends/wireguard.py](src/vpn_backends/wireguard.py) : transmet les opérations au CLI installé sur l’hôte VPN via SSH. [src/scheduler/leases.py](src/scheduler/leases.py) réconcilie actuellement les pairs et leurs adresses, mais pas des droits de destination distincts.
- [src/api/common/repositories/profiles.py](src/api/common/repositories/profiles.py) : `import_missing` initialise les profils sans remplacer les politiques déjà administrées en base. Ne pas supposer qu’une modification du YAML remplace automatiquement les politiques persistées.

Point technique essentiel : les `AllowedIPs` du pair côté serveur servent au routage vers ce pair et à la validation de ses adresses sources ; ce ne sont pas des autorisations de destination. Un préfixe exact ne peut pas appartenir simultanément à plusieurs pairs sur une même interface. Il faut donc distinguer les adresses VPN clientes, utilisées côté serveur, des réseaux autorisés du profil, utilisés pour le filtrage serveur et les `AllowedIPs` côté client. Supprimer uniquement le contrôle de chevauchement actuel ne résout pas le problème.

### 4.3 Décisions complémentaires et contrats à préciser

- [x] Retenir une allocation automatique persistante par équipement/interface ; les plages IPv4/IPv6 sont configurables dans les profils et doivent être cohérentes entre profils partageant une interface.
- [x] Retenir un seul bail réservé ou actif par utilisateur/appareil/profil et permettre plusieurs profils simultanés pour le même appareil ; le pair n’est retiré qu’après le dernier bail.
- [x] Placer endpoint, clé publique serveur et plages VPN dans les profils ; vérifier leur cohérence pour une interface partagée.
- [x] Conserver `interface` dans le YAML et `lease_target` dans l’API et la base, avec une conversion explicite dans `BackendConfig.access_profiles`.
- [x] Garder nftables comme prérequis externe : recommandations sur stdout et inclusion optionnelle dans le script seulement ; aucune application par l’installeur, aucun contrôle ni aucune réconciliation nftables au runtime.
- [x] Générer et conserver les clés privées côté client ; ne pas les transmettre ni les conserver côté serveur. Prévoir le parcours d’un équipement déjà enregistré.
- [x] Obtenir l’autorisation d’implémenter et d’adapter les tests aux scénarios de 4.7, corrigés selon la responsabilité externe du pare-feu.

### 4.4 Package CLI

- [x] Conserver `VPNLease.addresses` pour les adresses du pair, distinctes des destinations du bail ; valider et normaliser les CIDR avant tout appel au driver privilégié.
- [x] Vérifier les opérations locales `backend wg leases apply/delete/get/ls` avec les adresses clientes, y compris IPv4/IPv6 ; aucune commande, dépendance ou permission nftables ajoutée.
- [x] Préserver l’idempotence et la compensation du provisionnement, avec maintien du pair partagé tant qu’un autre bail le nécessite.
- [x] Ajouter `user leases configuration` : paramètres publics JSON/YAML ou assemblage local avec `--private-key-file` et `--output`, contrôle via `wg pubkey`, fichier neuf privé `0600`, sans impression ni transmission de la clé privée.
- [x] Mettre à jour l’exemple [cli/docs/examples/profiles/profile-create.yaml](cli/docs/examples/profiles/profile-create.yaml), la référence et les documentations françaises et anglaises ; les entrées de création des baux restent des identifiants d’appareil/profil, sans réseaux fournis par l’utilisateur.
- [x] Construire wheel et archive source CLI puis exécuter les tests contre la wheel installée, pas seulement contre le checkout. Utiliser le CLI distant et l’image serveur issus de la même révision, sans compatibilité avec l’ancien schéma.

### 4.5 Package Installation

- [x] Adapter [scripts/install/configure.py](scripts/install/configure.py) : questionnaire centré sur les profils, connexion réutilisée pour une interface partagée, durées et destinations indépendantes.
- [x] Valider et générer les profils et leurs paramètres clients ; rejeter l’ancien format sans conversion.
- [x] Afficher les propositions nftables sur stdout et proposer leur inclusion commentée dans le script, sans application par l’installeur ou exécution des commentaires par le script. Ne pas modifier le pare-feu ni les permissions du compte distant.
- [x] Vérifier la liste de modules et templates de [scripts/install/build-package.sh](scripts/install/build-package.sh) : elle inclut déjà les dépendances de cette évolution ; aucun ajout au script de packaging nécessaire.
- [x] Actualiser [scripts/install/PACKAGE-README.md](scripts/install/PACKAGE-README.md), [INSTALL.md](INSTALL.md), le README généré et la documentation de déploiement.
- [x] Vérifier checksum, extraction, imports isolés, validation des trois profils et rendu des artefacts depuis l’archive autonome ; vérifier que le workflow de release utilise le même constructeur. Aucune publication GitHub effectuée.

### 4.6 Image Podman : API, persistance, scheduler et navigateur

- [x] Implémenter les profils déclarant leur interface dans `BackendConfig`, les cibles et l’import initial ; fournir les trois profils sur `wg0` dans [src/config/backend_config.yml](src/config/backend_config.yml).
- [x] Persister endpoint, clé publique serveur et plages dans `ProfilePolicy`, ainsi que les allocations dans `PeerAllocation` ; aucune migration, conversion ou suppression automatique des données existantes.
- [x] Allouer transactionnellement les adresses persistantes par appareil/interface et contrôler les doublons par utilisateur/appareil/profil ; autoriser les destinations communes. Sérialiser aussi la validation des paramètres techniques partagés.
- [x] Séparer `addresses` et `networks` dans le document immuable du bail, avec endpoint et clé publique serveur ; conserver le transport SSH et les contrôles d’autorisation existants.
- [x] Adapter le scheduler aux pairs partagés, à la révocation partielle et au retrait après le dernier bail ; conserver compensation et réconciliation WireGuard, sans opération nftables.
- [x] Documenter les limites du filtrage externe, des expirations partielles et des fichiers clients téléchargés, qui restent des instantanés sans rafraîchissement automatique.
- [x] Exposer `GET /api/v1/users/me/leases/<id>/configuration`, réservé au propriétaire d’un bail actif et provisionné, avec `Cache-Control: no-store`, paramètres publics et destinations des baux actifs du pair.
- [x] Ajouter le téléchargement navigateur avec lecture locale d’une clé ou configuration existante, vérification X25519 avec WebCrypto et assemblage local ; aucune clé privée transmise au serveur.
- [x] Construire et exécuter l’image non-root sans capacités réseau supplémentaires. Ajouter les sources de l’installeur uniquement dans la cible Docker de test pour ses tests de rendu.
- [x] Actualiser architecture, sécurité, déploiement et exploitation en français et anglais.

### 4.7 Tests existants à adapter et couverture à prévoir

Les suites existantes et leurs fixtures ont été réutilisées. Les résultats exécutés sont consignés en 4.8 ; les essais externes non réalisés restent explicitement décochés.

- [x] Configuration et API : adapter les fixtures et vérifier chargement, profils partagés, politiques distinctes, incohérence des paramètres d’interface, ancien format refusé, propriété et états des baux.
- [x] Réservations : remplacer le refus des destinations communes par l’allocation d’adresses distinctes, vérifier la concurrence, les doublons par profil, la stabilité, IPv6 seul, double pile et épuisement des plages.
- [x] CLI : vérifier les CIDR rejetés avant appel au driver, l’export privé sans fuite ni écrasement et les opérations WireGuard répétables ; exécuter les tests contre la wheel installée.
- [ ] Intégration réseau réelle : adapter [tests/test_scheduler/test_wireguard_integration.py](tests/test_scheduler/test_wireguard_integration.py) et les environnements Compose pour connecter plusieurs pairs simultanés sur `wg0`, pas uniquement lire les `AllowedIPs` avec `wg show`.
- [ ] Sécurité réseau : vérifier les adresses sources autorisées par WireGuard et l’absence d’opération nftables à la création, expiration, suppression ou réconciliation d’un bail. Les tests de restrictions de destinations nécessitent un pare-feu externe configuré par l’environnement, sans attribuer cette garantie à TTL-LAMa.
- [x] Cycle de vie : vérifier application, expiration, révocation, retrait d’affectation, modification de politique, concurrence avec révocation, erreurs SSH, conservation du pair partagé et retrait après le dernier bail ; les anciens tests de compensation restent passants.
- [ ] Réconciliation : vérifier les redémarrages de l’application et de l’hôte VPN, la restauration des pairs manquants et le retrait des pairs expirés ou inconnus dans le périmètre géré ; aucune lecture ni écriture du pare-feu.
- [x] Configuration cliente : tester les paramètres, les refus entre utilisateurs, les états non utilisables et le cache ; vérifier dans le navigateur une clé incorrecte refusée, un Blob correctement assemblé, un lien de téléchargement et un GET sans corps contenant la clé ; contrôler le rendu mobile.
- [x] Installation : vérifier stdout, inclusion commentée ou refus, absence d’exécution de commandes au rendu et fonctionnement depuis l’archive extraite. Le questionnaire des profils réutilise les connexions par interface.
- [x] Packages livrés : construire archive autonome, wheel/source CLI et image locale ; tester les parcours contre le serveur et le CLI distant de cette révision.
- [x] Adapter [cli/compose.test.yml](cli/compose.test.yml) pour construire l’image du dépôt ; conserver les capacités `NET_ADMIN` limitées aux conteneurs réseau de test. Aucun changement de pare-feu ne nécessite une adaptation des autres lanceurs ou de la CI.
- [x] Consigner les commandes, résultats et limites en 4.8 ; aucune transition historique n’est ajoutée aux critères.

### 4.8 Résultats de l’implémentation du 16 novembre 2026

- Serveur dans l’image de test : **230 passed, 2 skipped**, avec le test d’intégration Dex exclu car ce fournisseur n’était pas lancé. Les scénarios de bases externes et de recréation réelle avec volume n’ont pas été relancés pour cette évolution.
- CLI issu de la wheel installée hors des sources : **139 passed**. Version de développement du paquet : `0.1.0`, sans publication ni commit.
- Intégration Compose avec serveur reconstruit, backend SSH et vrai WireGuard : **18 passed**, dont profils simultanés sur un appareil, configuration agrégée, révocation partielle et driver double pile.
- Archive d’installation construite avec l’étiquette locale `profiles-final` : checksum valide, imports provenant exclusivement de l’archive extraite, validation des trois profils et rendu du script commenté réussis.
- Navigateur : connexion, refus d’une mauvaise clé, validation X25519 d’une clé correcte, Blob contenant l’adresse et les destinations attendues, lien proposant `wireguard-1.conf`, GET de paramètres sans corps, champ local effacé et absence de débordement à 375 px. L’événement Playwright `download` n’est pas remonté par le navigateur intégré ; le Blob et le clic du lien ont été contrôlés, pas l’enregistrement sur disque par ce navigateur.
- Aucun diagnostic sur les fichiers Python modifiés contrôlés ; syntaxe JavaScript et exemples YAML validés. Aucune référence nftables/iptables dans les sources runtime du serveur ou du CLI.

Principales commandes exécutées, depuis la racine du dépôt :

```sh
podman build --target test -f src/Dockerfile -t localhost/ttl-lama:profiles-test .
podman run --rm -e TTL_LAMA_CONFIG_FILE=/dev/null --entrypoint python \
  localhost/ttl-lama:profiles-test -m pytest -q -p no:cacheprovider \
  --ignore=tests/test_auth/test_oidc_integration.py --tb=short
CLI_DIST=$(mktemp -d /tmp/ttlama-cli-final-XXXXXX)
.venv/bin/python -m build --wheel --sdist --outdir "$CLI_DIST" cli
.venv/bin/python -m pip install --no-deps --target "$CLI_DIST/installed" "$CLI_DIST/"*.whl
PYTHONPATH="$CLI_DIST/installed" .venv/bin/python -m pytest cli/tests --ignore=cli/tests/integration -q
INSTALLER_DIST=$(mktemp -d /tmp/ttlama-installer-final-XXXXXX)
scripts/install/build-package.sh profiles-final "$INSTALLER_DIST"
podman compose -p ttl-lama-profiles-final -f cli/compose.test.yml up \
  --build --abort-on-container-exit --exit-code-from cli-tests
```

Pour rejouer Compose, utiliser des conteneurs neufs ou l’option `--force-recreate` : le script SSH de ce banc ne doit pas être relancé dans un ancien conteneur contenant sa clé temporaire. Les tests racine et CLI doivent être exécutés séparément, leurs paquets `tests` entrant en conflit dans une invocation pytest commune. Pour tester les sources CLI, utiliser `PYTHONPATH=cli/src` ; sinon l’environnement local peut importer une ancienne distribution installée.

Les cases encore ouvertes en 4.7 concernent les essais de trafic et de redémarrage sur une infrastructure réseau réelle, notamment les refus de destinations sous pare-feu externe. Ils ne sont pas remplacés par des assertions sur `wg show`, et TTL-LAMa ne doit jamais être étendu à la gestion dynamique de nftables pour les satisfaire.
