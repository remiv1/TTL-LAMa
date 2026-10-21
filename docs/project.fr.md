# Projet

Ce document résume les usages visés de TTL-LAMa, ses principes, sa feuille de route et son état actuel.

## Cas d’usage

- **Homelab :** fournir un accès d’administration distant temporaire sans conserver des accès VPN permanents sur chaque appareil.
- **Infrastructure auto-hébergée :** contrôler les accès aux serveurs, NAS et interfaces d’administration internes.
- **Maintenance :** fournir un profil limité à une ressource et à une durée pour une intervention ponctuelle.
- **Petite organisation :** centraliser l’attribution et la révocation d’accès temporaires sans imposer un fournisseur d’identité particulier.
- **Infrastructure existante :** intégrer un fournisseur OIDC et une base de données existants tout en conservant la gestion des baux dans TTL-LAMa.
- **Automatisation :** permettre à terme à d’autres systèmes de demander ou superviser des accès temporaires selon les politiques définies par l’administrateur.

## Principes du projet

### Faire une chose clairement

Gérer des baux d’accès à durée limitée. TTL-LAMa n’a pas vocation à devenir une plateforme générale d’administration réseau.

### Rester déployable

Une installation autonome doit pouvoir tenir dans un conteneur unique. Le déploiement minimal ne doit pas nécessiter d’infrastructure complexe.

### Rester configurable

La politique d’infrastructure est déclarative et appartient à l’opérateur, pas à l’interface utilisateur.

### Être sécurisé par conception

Tout accès possède un cycle de vie. L’expiration et la révocation sont des invariants du modèle, et non des fonctionnalités optionnelles ajoutées après coup.

### Séparer le métier des implémentations

L’identité, la persistance et les backends d’accès sont des abstractions autour du modèle de bail. WireGuard, SQLite et OIDC sont des implémentations, pas le cœur conceptuel du projet.

### Rester ouvert

TTL-LAMa a vocation à être open source et adapté à l’auto-hébergement.

## Feuille de route

### Phase 0 : conception

- [ ] Définir le modèle de menace
- [ ] Définir le modèle `Identity / Device / Profile / Lease`
- [ ] Définir la machine à états des baux
- [ ] Définir les formats de configuration et de profils d’accès
- [ ] Définir les abstractions d’authentification, de persistance et de backend d’accès
- [ ] Définir le modèle d’audit

### Phase 1 : prototype autonome

- [ ] Déploiement dans un conteneur unique
- [ ] Authentification interne et multifacteur
- [ ] Persistance SQLite
- [ ] Backend WireGuard
- [ ] Gestion des appareils et enregistrement des clés publiques
- [ ] Profils d’accès et baux à durée déterminée
- [ ] Expiration automatique et révocation manuelle
- [ ] Réconciliation et journal d’audit

### Phase 2 : intégration

- [ ] Authentification externe et OIDC
- [ ] PostgreSQL
- [ ] Associations entre identités externes et profils
- [ ] Health checks, métriques et observabilité
- [ ] Amélioration des fonctions d’audit

### Phase 3 : extensibilité

- [ ] Stabiliser l’interface des backends d’accès
- [ ] Étudier d’autres mécanismes d’authentification et d’autres backends
- [ ] Processus d’approbation optionnels
- [ ] API d’automatisation et intégrations tierces

## Mascotte

La mascotte de TTL-LAMa est un **lama gardien**. Son identité visuelle combine :

- un lama, identité reconnaissable du projet ;
- une casquette, qui représente son rôle de gardien ;
- un chronomètre, qui représente la durée de vie limitée des accès.

Le chronomètre porte la promesse centrale du projet : **tout accès a une durée de vie**.

## État, contributions et licence

> **Conception initiale / prototype**

TTL-LAMa est actuellement au stade de la conception. Les API, formats de configuration, schémas de données et choix architecturaux sont préliminaires et peuvent évoluer pendant l’implémentation. L’objectif initial est de construire un modèle simple, explicite, auditable, testable, sécurisé et extensible sans complexité inutile.

Les discussions et contributions sont particulièrement utiles sur le modèle de menace, l’architecture de sécurité, le modèle identité/appareil/profil/bail, l’authentification, les intégrations OIDC et WireGuard, l’isolation du conteneur, les privilèges Linux, la persistance, la réconciliation, les politiques réseau et l’audit.

**Licence :** à déterminer avant la première version publique stable.
