# Modèle de sécurité

TTL-LAMa est un composant d’infrastructure sensible : il contrôle des accès réseau et peut nécessiter davantage de privilèges qu’une application web ordinaire. Sa conception met donc l’accent sur des permissions limitées, des politiques explicites, la révocation automatique et la traçabilité.

## Privilèges minimaux

TTL-LAMa ne doit demander que les capacités système nécessaires au backend configuré. Une exécution entièrement privilégiée doit être évitée lorsqu’un ensemble de capacités plus limité suffit.

## Surface publique minimale

La surface destinée aux utilisateurs doit se limiter aux opérations réellement nécessaires :

- authentification ;
- gestion de ses propres appareils ;
- demande d’accès ;
- consultation de ses propres accès ;
- révocation de ses propres accès.

La configuration de l’infrastructure n’appartient pas à cette interface. Aucune interface générale d’administration permettant de modifier dynamiquement la configuration réseau n’est prévue.

## Politiques déclaratives

Les administrateurs définissent les politiques dans la configuration et les utilisateurs choisissent uniquement parmi les possibilités proposées. Un utilisateur ne doit pas pouvoir soumettre des règles réseau arbitraires ni dépasser les limites d’un profil d’accès.

## Moindre privilège

Chaque profil ne doit fournir que les accès nécessaires à son usage. Par exemple, un profil de maintenance peut autoriser SSH vers un seul serveur, tandis qu’un profil d’administration peut donner accès à un réseau de serveurs défini et aux seules interfaces nécessaires.

Un accès VPN ne signifie pas nécessairement l’accès à l’ensemble du réseau privé.

## Révocation automatique

L’expiration est un invariant du modèle de sécurité. Un bail expiré ne doit pas simplement apparaître comme `EXPIRED` dans l’application ; il doit entraîner :

```text
ACCESS = ABSENT
```

Il en va de même pour un bail révoqué explicitement. La réconciliation doit rétablir cet invariant même si TTL-LAMa était indisponible au moment de l’expiration.

## Traçabilité

Les opérations sensibles doivent produire des événements d’audit, notamment :

- les authentifications et leurs échecs ;
- l’enregistrement et la révocation d’appareils ;
- la création et l’activation de baux ;
- l’expiration et la révocation manuelle de baux ;
- les échecs de provisionnement ;
- la réconciliation.

Les journaux d’audit ne doivent contenir ni clés privées ni credentials.
