# TTL-LAMa 🦙⏱️

[English](../README.md) | Français

> **Time-To-Live Lease Access Manager**
>
> **Des accès temporaires. Une révocation automatique.**

TTL-LAMa est un gestionnaire open source conçu pour accorder des accès temporaires et limités dans le temps à des réseaux privés. Au lieu d’attribuer des accès VPN permanents, il considère chaque autorisation comme un **bail** (*lease*) doté d’une date d’expiration.

Après authentification, l’utilisateur choisit un profil d’accès autorisé et un appareil ; l’accès est accordé pour une durée limitée. À l’expiration ou à la révocation du bail, l’accès réseau correspondant est supprimé. Le premier backend prévu est **WireGuard**.

## Objectifs

- Des accès réseau à durée limitée, avec expiration et révocation automatiques.
- Des profils définis par l’administrateur et une identité VPN distincte par appareil.
- Plusieurs modes d’authentification et une persistance locale ou externe.
- Un déploiement autonome et une architecture extensible à d’autres backends.

TTL-LAMa gère des baux d’accès ; ce n’est ni une interface générale d’administration réseau, ni un remplacement de WireGuard, ni un fournisseur d’identité généraliste. Les politiques d’infrastructure restent sous le contrôle de l’opérateur.

## Documentation

| Sujet | Français | English |
| --- | --- | --- |
| Architecture et modèle métier | [Architecture](docs/architecture.fr.md) | [Architecture](docs/architecture.md) |
| Déploiement et configuration | [Déploiement](docs/deployment.fr.md) | [Deployment](docs/deployment.md) |
| Cycle de vie et réconciliation | [Fonctionnement](docs/operations.fr.md) | [Operations](docs/operations.md) |
| Principes de sécurité | [Sécurité](docs/security.fr.md) | [Security](docs/security.md) |
| Cas d’usage, feuille de route et état | [Projet](docs/project.fr.md) | [Project](docs/project.md) |

## État du projet

TTL-LAMa est au stade initial de la conception et du prototype. Les API, formats de configuration, schémas de données et choix architecturaux sont préliminaires et peuvent évoluer pendant l’implémentation. Voir la [présentation du projet](docs/project.fr.md) pour la feuille de route et les sujets de contribution.

**Licence :** à déterminer avant la première version publique stable.

---

> **TTL-LAMa 🦙⏱️**
> *Time-To-Live Lease Access Manager*
> **Des accès temporaires. Une révocation automatique.**
