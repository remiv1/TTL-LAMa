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
- [x] Vérifier la persistance des données après redémarrage du conteneur.
- [x] Vérifier que les secrets sont montés séparément, exclus de l’image et absents des journaux.
- [x] Ajouter un contrôle de santé utilisable par le déploiement.
- [x] Documenter une procédure complète d’installation et de mise à jour, en mettant à jour `INSTALL.md` pour refléter l’installeur et le layout réellement généré.

### 2.2 Terminer l’authentification interne

- [x] Comparer les fonctions déjà présentes à la cible : création et gestion des comptes, sessions, protection CSRF et limitation des tentatives.
- [x] Décider si l’authentification multifacteur est nécessaire au prototype et définir les facteurs acceptés.
- [ ] Implémenter les fonctions manquantes sans stocker de secrets en clair.
- [x] Tester les succès, refus, expirations de session, révocations et cas limites.
- [ ] Documenter la création du compte administrateur et la récupération d’accès.

### 2.3 Mettre en place la persistance SQLite

- [x] Définir les tables et contraintes du modèle métier validé.
- [ ] Implémenter les dépôts pour les identités, appareils, profils, baux et événements d’audit.
- [ ] Vérifier les transactions lors des opérations qui modifient à la fois un bail et son état de provisionnement.
- [ ] Tester la création, la lecture, la mise à jour, la suppression et les migrations sur une base temporaire.

### 2.4 Implémenter la gestion des appareils

- [x] Définir les opérations d’enregistrement, de consultation et de révocation d’un appareil.
- [x] Enregistrer les informations nécessaires à un appareil, dont la clé publique du client.
- [x] Vérifier qu’un utilisateur ne peut gérer que ses propres appareils.
- [ ] Valider le format des clés publiques et empêcher les doublons.
- [ ] Tester les clés invalides, les doublons et la révocation d’un appareil ayant un bail actif.

### 2.5 Implémenter les profils et les baux

- [x] Charger et valider les profils d’accès depuis la configuration déclarative.
- [x] Exposer uniquement à l’utilisateur les profils auxquels il est autorisé.
- [x] Créer un bail lié à une identité, un appareil et un profil, avec une expiration calculée côté serveur.
- [x] Refuser les durées hors limites et les réseaux fournis directement par l’utilisateur.
- [x] Permettre à l’utilisateur de consulter et révoquer ses propres baux.
- [x] Tester les autorisations, limites de durée et transitions principales du cycle de vie.
- [ ] Tester le chargement des profils depuis le fichier configuré au démarrage de l’application.

### 2.6 Implémenter le backend WireGuard

- [x] Retenir une communication SSH du conteneur applicatif vers l’hôte VPN; ne pas confondre ce flux avec les commandes locales du CLI.
- Pour le MVP, utiliser une clé SSH dédiée plutôt que des certificats SSH; réévaluer les certificats si une CA est disponible.
- [x] Automatiser de façon idempotente la création d’un compte distant dédié non-root et l’application des permissions minimales.
- [x] Limiter sudo aux opérations WireGuard nécessaires; ne jamais accorder un accès sudo générique.
- [ ] Générer et installer une clé SSH dédiée, épingler `known_hosts`, puis documenter la rotation et la révocation de la clé.
- [x] Monter la clé privée comme secret hors de l’image et configurer les paramètres SSH non secrets dans les fichiers de configuration.
- [ ] Relier l’exécuteur SSH existant au backend serveur et au cycle de vie des baux.
- [ ] Implémenter côté serveur l’ajout, la lecture et la suppression idempotente d’un pair via l’hôte VPN.
- [ ] Associer chaque pair provisionné à un appareil et à un bail.
- [ ] Vérifier que les réseaux appliqués proviennent exclusivement du profil autorisé.
- [ ] Valider côté serveur l’état et l’autorisation du bail avant toute opération privilégiée.
- [ ] Tester les erreurs SSH et WireGuard, ainsi que l’absence de faux état actif après un échec.
- [ ] Documenter et tester l’installation côté hôte : compte, permissions, sudoers, `known_hosts`, secrets et configuration WireGuard.

### 2.7 Garantir expiration, révocation et réconciliation

- [ ] Enregistrer dans le scheduler du conteneur les tâches périodiques d’expiration et de réconciliation.
- [ ] Déclencher l’expiration des baux arrivés à échéance.
- [ ] Supprimer les accès associés aux baux expirés ou révoqués.
- [ ] Au démarrage et périodiquement, comparer l’état désiré en base avec l’état WireGuard de l’hôte.
- [ ] Définir la résolution des divergences, y compris les pairs inconnus du serveur et les indisponibilités du backend.
- [ ] Corriger les écarts sans créer de doublons et rendre les opérations répétables.
- [ ] Tester les arrêts et redémarrages autour d’une expiration, ainsi que les indisponibilités du backend.
- [ ] Tracer les échecs et corrections dans les événements d’audit.

## 3. Intégrer des services externes

### 3.1 Terminer l’intégration OIDC

- [x] Vérifier le flux existant contre les exigences OIDC retenues et les contrôles de sécurité attendus.
- [ ] Gérer les erreurs d’échange, d’état, de nonce, d’émetteur et de validation des jetons.
- [x] Définir la correspondance stable entre le sujet externe et l’identité locale.
- [x] Tester le flux avec un fournisseur simulé et documenter un exemple de configuration.

### 3.2 Ajouter les bases de données externes

- [x] Confirmer les moteurs réellement visés pour la première version intégrée.
- [x] Vérifier les ~~migrations~~, contraintes et types nécessaires sur chaque moteur retenu.
- [x] Ajouter des tests d’intégration isolés pour chaque moteur pris en charge.

### 3.3 Ajouter l’observabilité

- [ ] Définir les contrôles de santé et les indicateurs nécessaires à l’exploitation.
- [ ] Exposer les métriques sans inclure d’identifiants ou de secrets inutiles.
- [x] Journaliser explicitement les succès et les échecs des opérations sensibles, dont l’application et la suppression d’un bail ainsi que les réconciliations.
- [x] Appliquer le format et la politique de niveaux définis en 1.6; centraliser les journaux de l’API et du scheduler dans des fichiers historiques séparés par niveau, avec rotation et conservation maîtrisées.
- [x] Vérifier par des tests et une revue des chemins d’erreur qu’aucun secret ou contenu de fichier secret n’apparaît dans les journaux.
- [x] Documenter les alertes utiles, notamment les échecs de réconciliation et de provisionnement.

## 4. Préparer l’extensibilité et la publication

### 4.1 Stabiliser les interfaces d’extension

- [ ] Vérifier que le contrat du backend d’accès couvre les opérations réellement nécessaires au cycle de vie.
- [ ] Documenter les garanties d’idempotence, les erreurs et les responsabilités de chaque backend.
- [x] Ajouter un backend de test permettant de valider le cœur métier sans infrastructure réseau.

### 4.2 Évaluer les extensions futures

- [ ] Recueillir un cas d’usage concret avant de retenir un nouveau fournisseur d’identité ou backend d’accès.
- [ ] Comparer les impacts de sécurité, d’exploitation et de maintenance.
- [ ] N’ajouter une extension qu’après validation de son périmètre et de ses critères d’acceptation.

### 4.3 Évaluer les approbations et l’API d’automatisation

- [ ] Définir les cas nécessitant une approbation et les rôles autorisés à décider.
- [ ] Décrire les états et délais supplémentaires avant de modifier le cycle de vie des baux.
- [ ] Définir les clients, permissions, limites et traces d’audit de l’API d’automatisation.
- [ ] Valider que les intégrations tierces ne peuvent ni élargir les profils ni contourner l’expiration.

### 4.4 Préparer une version publique

- [x] Choisir et documenter la licence avant une version stable.
- [ ] Vérifier que les instructions d’installation, de configuration, de mise à jour et de sauvegarde sont complètes.
- [ ] Définir une procédure de signalement des vulnérabilités et compléter les consignes de sécurité.
- [x] Exécuter les tests et contrôles de sécurité prévus pour une publication (CI/CD créé et fonctionnel)
- [ ] Définir les critères de version stable et les limites connues du produit.
