# Contribuer à TTL-LAMa

[English](../CONTRIBUTING) | Français

Merci de votre intérêt pour **TTL-LAMa** 🦙⏱️.

Ce document reste volontairement court. La vision, l’architecture et les principes du projet sont décrits dans le `README.md`.

## Avant de contribuer

- Vérifiez qu’une issue ou une Pull Request existante ne traite pas déjà le sujet.
- Pour une évolution importante ou un changement d’architecture, ouvrez d’abord une issue afin d’en discuter.
- Pour une correction simple, une Pull Request peut être proposée directement.

## Pull Requests

Une Pull Request doit idéalement :

- rester limitée à un sujet précis ;
- expliquer brièvement le problème et la solution proposée ;
- inclure ou adapter les tests lorsque cela est pertinent ;
- mettre à jour la documentation si le comportement ou la configuration change ;
- signaler explicitement tout impact sur la sécurité, les privilèges, le réseau, l’authentification ou la compatibilité.

## Qualité du code

Les contributions doivent privilégier :

- un code simple et lisible ;
- des responsabilités clairement séparées ;
- le principe du moindre privilège ;
- l’absence de secrets ou de clés privées dans le code et les journaux ;
- des dépendances supplémentaires uniquement lorsqu’elles sont justifiées.

Évitez d’introduire une abstraction ou une complexité qui ne répond pas à un besoin concret.

## Assets web

L’interface web utilise du SCSS et une copie locale de htmx. Après modification des sources, exécutez `npm ci` puis `npm run build` à la racine du dépôt. Le CSS compilé et les dépendances copiées sont conservés dans `src/api/web/static/` et intégrés à l’image applicative.

## Commits

Des messages de commit courts et explicites sont recommandés, par exemple :

```text
feat: add OIDC authentication
fix: revoke expired leases after restart
docs: update WireGuard configuration
test: cover device revocation
```

## Sécurité

TTL-LAMa gère des accès réseau. Les modifications concernant l’authentification, l’autorisation, les secrets, les clés, les privilèges système ou les backends d’accès doivent donc faire l’objet d’une attention particulière.

Ne publiez pas les détails d’une vulnérabilité exploitable dans une issue publique. La procédure de signalement sera décrite dans `SECURITY.md`.

## Licence

En soumettant une contribution à TTL-LAMa, vous acceptez qu’elle soit distribuée sous la licence du projet.

Merci de contribuer à **TTL-LAMa** 🦙⏱️.
