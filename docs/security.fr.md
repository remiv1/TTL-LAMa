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

Le filtrage des destinations relève de l’administrateur du routeur. TTL-LAMa gère uniquement les baux et les pairs WireGuard ; aucune opération runtime ne lit ni ne modifie nftables. L’installeur affiche des propositions et peut les inclure sous forme de commentaires dans le script de préparation, sans les appliquer. Les `AllowedIPs` du client sont modifiables : ce sont des paramètres de routage, pas une liste de contrôle d’accès imposée côté serveur.

## Socle applicatif

En production, la configuration doit fournir une clé Flask d’au moins 32 caractères et activer les cookies `Secure`. L’authentification est obligatoire : elle utilise soit les comptes internes, soit un fournisseur d’identité externe. Les cookies de session sont `HttpOnly` et `SameSite=Lax`; les requêtes modifiant l’état sont protégées contre les attaques CSRF.

Les secrets peuvent être montés sous `/run/secrets/` et référencés par des paramètres terminés par `_FILE`. Ils ne doivent apparaître ni dans les journaux ni dans l’image. Les jetons de session persistés sont stockés sous forme de condensat.

Le conteneur s’exécute sans privilèges root. Le changement de mode ou d’émetteur d’authentification ne supprime pas automatiquement les comptes existants : une migration explicite est requise.

## Révocation automatique

L’expiration change l’état du bail et libère sa réservation du pair WireGuard. Plusieurs profils peuvent avoir des baux simultanés pour un appareil/interface. Le pair est supprimé après la fin du dernier bail actif :

```text
FIN DU DERNIER BAIL ACTIF -> SUPPRESSION DU PAIR WIREGUARD
```

Il en va de même pour une révocation explicite. La réconciliation rétablit l’état désiré des pairs au redémarrage. Une expiration partielle ne retire pas de destination au pare-feu externe lorsqu’un autre bail conserve le pair. Une politique externe adaptée reste nécessaire ; TTL-LAMa ne garantit ni la révocation des destinations par profil ni le contrôle du suivi de connexion. Les configurations clientes téléchargées sont des instantanés et n’expirent pas automatiquement.

## Traçabilité

Les opérations sensibles doivent produire des événements d’audit, notamment :

- les authentifications et leurs échecs ;
- l’enregistrement et la révocation d’appareils ;
- la création et l’activation de baux ;
- l’expiration et la révocation manuelle de baux ;
- les échecs de provisionnement ;
- la réconciliation.

Les journaux d’audit ne doivent contenir ni clés privées ni credentials.
