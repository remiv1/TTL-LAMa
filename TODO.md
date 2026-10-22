# TODO TTL-LAMa

Cette liste décline la feuille de route de [docs/project.fr.md](docs/project.fr.md) en actions réalisables. Elle sert de suivi du travail, sans remplacer les décisions d’architecture.

Chaque grande ligne regroupe un chantier, chaque sous-tâche un résultat à obtenir et les cases à cocher les actions concrètes. Une case reste décochée tant que l’action n’a pas été vérifiée dans le code, la documentation ou les tests.

## 0. Qualifier l’état actuel

### 0.1 Établir le point de départ

- [ ] Lancer la suite de tests existante et noter les éventuels échecs initiaux.
- [ ] Vérifier les fonctionnalités présentes dans `src/auth/` et leurs tests, notamment les modes interne et OIDC.
- [ ] Recenser les implémentations présentes pour la configuration, la persistance, les profils, les appareils, les baux, le provisionnement et l’audit.
- [ ] Pour chaque sous-tâche ci-dessous, noter si elle est absente, partielle ou déjà réalisée, puis ajuster la liste sans supprimer les travaux utiles.

## 1. Finaliser la conception

### 1.1 Définir le modèle de menace

- [ ] Lister les actifs à protéger : identifiants, sessions, clés publiques, configuration, baux et accès réseau.
- [ ] Décrire les acteurs, les frontières de confiance et les interfaces exposées.
- [ ] Recenser les menaces liées à l’authentification, à l’autorisation, aux secrets, au conteneur et au backend réseau.
- [ ] Associer à chaque menace une mesure de réduction et un risque résiduel accepté.
- [ ] Vérifier que le modèle est cohérent avec [docs/security.fr.md](docs/security.fr.md).

### 1.2 Définir les concepts métier

- [ ] Décrire les attributs et identifiants d’une identité, d’un appareil, d’un profil et d’un bail.
- [ ] Définir les relations, contraintes d’unicité et règles de propriété entre ces concepts.
- [ ] Préciser les données persistées et celles qui ne doivent jamais être conservées, notamment les clés privées.
- [ ] Valider les cas d’usage principaux : plusieurs appareils, accès limités à un profil, révocation d’un appareil.
- [ ] Mettre à jour le document d’architecture avec le modèle retenu.

### 1.3 Définir le cycle de vie des baux

- [ ] Établir la liste minimale des états et les transitions autorisées.
- [ ] Définir les conditions de création, activation, expiration, révocation et échec.
- [ ] Écrire les invariants : un bail expiré ou révoqué ne doit plus donner accès au réseau.
- [ ] Définir le comportement des transitions répétées et des opérations concurrentes.
- [ ] Ajouter des scénarios couvrant les redémarrages et les erreurs de provisionnement.

### 1.4 Stabiliser la configuration

- [ ] Décrire les paramètres de l’application, les profils d’accès et leurs valeurs par défaut.
- [ ] Confirmer la priorité entre valeurs par défaut, YAML, variables d’environnement et fichiers de secrets.
- [ ] Définir les validations des profils : réseaux autorisés, durée par défaut et durée maximale.
- [ ] Documenter les erreurs de configuration et vérifier qu’elles échouent sans exposer de secret.
- [ ] Fournir des exemples de configuration valides et invalides.

### 1.5 Définir les contrats des composants

- [ ] Définir les opérations et erreurs attendues des backends de persistance.
- [ ] Définir les opérations et erreurs attendues des backends d’accès réseau.
- [ ] Définir la frontière entre authentification, identité métier et autorisation.
- [ ] Préciser les garanties transactionnelles nécessaires lors de la création ou de la révocation d’un bail.
- [ ] Vérifier que les contrats ne dépendent pas de WireGuard ou d’un fournisseur d’identité précis.

### 1.6 Définir l’audit

- [ ] Lister les événements sensibles à tracer et les informations nécessaires à leur diagnostic.
- [ ] Exclure des événements les mots de passe, secrets, jetons bruts et clés privées.
- [ ] Définir l’association d’un événement à une identité, un appareil, un bail et une date.
- [ ] Déterminer les règles de conservation et les modalités d’accès aux journaux.

## 2. Réaliser le prototype autonome

### 2.1 Valider le déploiement en conteneur

- [ ] Vérifier le démarrage reproductible avec le Compose de développement.
- [ ] Confirmer l’exécution sans privilèges root et documenter les permissions requises.
- [ ] Vérifier la persistance des données après redémarrage du conteneur.
- [ ] Vérifier que les secrets sont montés séparément, exclus de l’image et absents des journaux.
- [ ] Ajouter un contrôle de santé utilisable par le déploiement.
- [ ] Documenter une procédure complète d’installation et de mise à jour.

### 2.2 Terminer l’authentification interne

- [ ] Comparer les fonctions déjà présentes à la cible : création et gestion des comptes, sessions, protection CSRF et limitation des tentatives.
- [ ] Décider si l’authentification multifacteur est nécessaire au prototype et définir les facteurs acceptés.
- [ ] Implémenter les fonctions manquantes sans stocker de secrets en clair.
- [ ] Tester les succès, refus, expirations de session, révocations et cas limites.
- [ ] Documenter la création du compte administrateur et la récupération d’accès.

### 2.3 Mettre en place la persistance SQLite

- [ ] Définir les tables et contraintes du modèle métier validé.
- [ ] Créer la première migration et documenter son exécution.
- [ ] Implémenter les dépôts pour les identités, appareils, profils, baux et événements d’audit.
- [ ] Vérifier les transactions lors des opérations qui modifient à la fois un bail et son état de provisionnement.
- [ ] Tester la création, la lecture, la mise à jour, la suppression et les migrations sur une base temporaire.

### 2.4 Implémenter la gestion des appareils

- [ ] Définir les opérations d’enregistrement, de consultation et de révocation d’un appareil.
- [ ] Enregistrer uniquement les informations nécessaires, dont la clé publique du client.
- [ ] Vérifier qu’un utilisateur ne peut gérer que ses propres appareils.
- [ ] Tester les clés invalides, les doublons et la révocation d’un appareil ayant un bail actif.

### 2.5 Implémenter les profils et les baux

- [ ] Charger et valider les profils d’accès depuis la configuration déclarative.
- [ ] Exposer uniquement à l’utilisateur les profils auxquels il est autorisé.
- [ ] Créer un bail lié à une identité, un appareil et un profil, avec une expiration calculée côté serveur.
- [ ] Refuser les durées hors limites et les réseaux fournis directement par l’utilisateur.
- [ ] Permettre à l’utilisateur de consulter et révoquer ses propres baux.
- [ ] Tester les autorisations, limites de durée et transitions du cycle de vie.

### 2.6 Implémenter le backend WireGuard

- [ ] Décider comment le processus communique avec WireGuard et limiter les privilèges à cette méthode.
- [ ] Implémenter l’ajout, la lecture et la suppression idempotente d’un pair.
- [ ] Associer chaque pair provisionné à un appareil et à un bail.
- [ ] Vérifier que les réseaux appliqués proviennent exclusivement du profil autorisé.
- [ ] Tester les erreurs du backend et empêcher qu’un échec soit présenté comme un accès actif.
- [ ] Documenter la configuration requise côté hôte et côté WireGuard.

### 2.7 Garantir expiration, révocation et réconciliation

- [ ] Déclencher l’expiration des baux arrivés à échéance.
- [ ] Supprimer les accès associés aux baux expirés ou révoqués.
- [ ] Au démarrage et périodiquement, comparer l’état désiré en base avec l’état du backend.
- [ ] Corriger les écarts sans créer de doublons et rendre les opérations répétables.
- [ ] Tester les arrêts et redémarrages autour d’une expiration, ainsi que les indisponibilités du backend.
- [ ] Tracer les échecs et corrections dans les événements d’audit.

## 3. Intégrer des services externes

### 3.1 Terminer l’intégration OIDC

- [ ] Vérifier le flux existant contre les exigences OIDC retenues et les contrôles de sécurité attendus.
- [ ] Gérer les erreurs d’échange, d’état, de nonce, d’émetteur et de validation des jetons.
- [ ] Définir la correspondance stable entre le sujet externe et l’identité locale.
- [ ] Tester le flux avec un fournisseur simulé et documenter un exemple de configuration.

### 3.2 Ajouter les bases de données externes

- [ ] Confirmer les moteurs réellement visés pour la première version intégrée.
- [ ] Vérifier les migrations, contraintes et types nécessaires sur chaque moteur retenu.
- [ ] Ajouter des tests d’intégration isolés pour chaque moteur pris en charge.
- [ ] Documenter les paramètres de connexion, les sauvegardes et les mises à niveau de schéma.

### 3.3 Associer identités externes et profils

- [ ] Définir les règles d’association entre groupes ou attributs externes et profils d’accès.
- [ ] Valider ces règles côté serveur à chaque demande de bail.
- [ ] Tester les attributs absents, inconnus, modifiés et les accès révoqués.
- [ ] Documenter la configuration des associations et leur comportement en cas d’indisponibilité de l’IdP.

### 3.4 Ajouter l’observabilité

- [ ] Définir les contrôles de santé et les indicateurs nécessaires à l’exploitation.
- [ ] Exposer les métriques sans inclure d’identifiants ou de secrets inutiles.
- [ ] Structurer les journaux pour suivre un bail de sa création à sa révocation.
- [ ] Documenter les alertes utiles, notamment les échecs de réconciliation et de provisionnement.

## 4. Préparer l’extensibilité et la publication

### 4.1 Stabiliser les interfaces d’extension

- [ ] Vérifier que le contrat du backend d’accès couvre les opérations réellement nécessaires au cycle de vie.
- [ ] Documenter les garanties d’idempotence, les erreurs et les responsabilités de chaque backend.
- [ ] Ajouter un backend de test permettant de valider le cœur métier sans infrastructure réseau.

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

- [ ] Choisir et documenter la licence avant une version stable.
- [ ] Vérifier que les instructions d’installation, de configuration, de mise à jour et de sauvegarde sont complètes.
- [ ] Définir une procédure de signalement des vulnérabilités et compléter les consignes de sécurité.
- [ ] Exécuter les tests et contrôles de sécurité prévus pour une publication.
- [ ] Définir les critères de version stable et les limites connues du produit.
