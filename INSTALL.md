# Plan d’installation TTL-LAMa

> L’installeur est implémenté dans `scripts/install/`. Il génère un bundle de configuration et affiche les commandes Podman sans les exécuter.

## Parcours de configuration

```text
1. Hôte application et hôte VPN identiques ?
2. Authentification : interne ou OIDC ?
   ├── OIDC : fournisseur, client, secret, URL de retour
   └── Interne : compte administrateur initial
3. Base de données ?
   └── Oui : moteur, adresse, port, base, schéma, identifiants
4. Application : environnement, debug, clé secrète, journaux
5. Ports : écoute du serveur et port publié
6. Hasher : paramètres Argon2id
7. Sécurité : HTTPS, cookies, session, origines
8. Backend : WireGuard ou OpenVPN, interfaces et profils
9. SSH : hôte, port, utilisateur, clés, known_hosts, timeout
```

## Questions détaillées

1. **Hôtes** — Le conteneur applicatif sera-t-il sur la même machine que le VPN ?
   - Oui : utiliser l’adresse de l’hôte accessible depuis le conteneur.
   - Non : demander séparément l’hôte applicatif et l’hôte VPN.
   - Dans les deux cas, conserver le conteneur non privilégié et le compte VPN dédié.

2. **Authentification** — Choisir `interne` ou `OIDC`.
   - **2bis OIDC** : émetteur, identifiant client, secret client, URL de callback et URL après connexion. Le nom de variable du secret figure dans `.env.example`; l’utilisateur renseigne sa valeur dans `.env`.
   - **2bis interne** : nom et mot de passe du compte administrateur initial. Le mot de passe est saisi sans affichage et écrit dans le YAML initial pour créer le compte; le compte et son credential persistent ensuite dans la base.

    > L'administrateur de l'application devra supprimer le mot de passe initial de l'administrateur une fois la persistance réalisée

3. **Base de données** — Choisir le moteur.
   - SQLite : chemin du fichier.
   - Base externe : moteur, hôte, port, nom de base, schéma et compte.
   - **3bis** : demander les paramètres de connexion nécessaires au moteur choisi; le nom de variable du mot de passe figure dans `.env.example` et sa valeur est renseignée dans `.env`.

4. **Application** — Environnement, mode debug, niveau de journalisation et clé Flask.
   - Générer une clé secrète si aucune n’est fournie; privilégier `secret_key_file` plutôt qu’une valeur dans le YAML.
   - Désactiver le debug en production.

5. **Ports** — Port d’écoute dans le conteneur et port publié sur l’hôte. Vérifier les conflits et afficher l’URL résultante.

6. **Hasher** — Configurer les paramètres Argon2id : coût temporel, mémoire, parallélisme et longueurs du hash et du sel.

7. **Sécurité applicative** — Choisir le profil de sécurité, puis régler HTTPS obligatoire, attributs des cookies, durée de session et origines autorisées.

8. **Backend** — Choisir `WireGuard` ou `OpenVPN`, puis décrire les interfaces et profils : nom, description, réseaux et durées autorisées.

9. **SSH** — Hôte VPN, port, utilisateur dédié, chemin de la clé d’identité, fichier `known_hosts` et délai de connexion. Générer une clé dédiée si nécessaire; ne jamais désactiver la vérification de l’hôte.

## SSH host key setup (WireGuard)

The generated `vpn-host-setup.sh` provisions the restricted VPN account and installs the client's public key in that account's `authorized_keys`. These are different keys: the client key (`wireguard-ssh-key.pub`) must not be used as the SSH server host key.

After running `vpn-host-setup.sh` on the VPN host, the script attempts to scan the local SSH service on the configured port. It prints the ED25519 fingerprint and a complete `known_hosts` entry using the VPN host and port configured for TTL-LAMa. The scan must reach the same SSH service that the application container reaches.

Verify the printed fingerprint through a trusted channel before using the entry. On a standard OpenSSH server, compare it with the fingerprint of the active ED25519 host public key, for example:

```sh
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

If the SSH daemon uses a custom `HostKey` path, check that key's `.pub` file instead. Do not copy the fingerprint into `ssh_known_hosts`: it is only for comparison. Copy the complete entry printed by the setup script into `etc/ttl-lama/ssh_known_hosts` on the application host. For a non-default port, the entry must identify the endpoint as `[host]:port`; the setup script formats this automatically. Keep `StrictHostKeyChecking` enabled.

If startup reports `No ED25519 host key is known`, check that the mounted file contains an entry for the exact configured host and port and that the entry includes the full public key (key type and base64 key data), not just an `SHA256:` fingerprint. For example, inspect the mounted file with:

```sh
podman exec ttl-lama ssh-keygen -F '[host.containers.internal]:39022' -f /etc/ttl-lama/ssh_known_hosts
```

After correcting the host entry on the application host, restart the container so startup reconciliation runs again.

## Déploiement prévu

```text
Questionnaire Python
        │ réponses validées
        ▼
Fichiers YAML + .env.example
        │
        ├──► install.sh (Bash) ──► vérifications + commandes Podman affichées
        │
        └──► script VPN généré ──SSH──► hôte VPN
                                      └─ commandes backend autorisées
```

L’image applicative est déjà construite avant cette étape. L’installeur n’exécute aucune commande Podman : il affiche `podman volume create` puis `podman run`, configuré avec l’image existante, les fichiers de configuration et secrets à monter, les ports et `--env-file .env`. L’opérateur vérifie les commandes affichées puis les exécute. Aucun `podman build` ni objet Podman pod n’est créé par ce parcours.

Le fichier `.env.example` contient les noms des variables attendues. L’utilisateur le copie en `.env` et complète les valeurs avant d’exécuter les commandes affichées. Le fichier `.env` n’est pas inclus dans l’image et ne doit pas être ajouté au dépôt. Le mot de passe initial de l’administrateur reste dans le YAML initial, conformément au bootstrap de l’application et devra être supprimé par l'administrateur après la persistance réalisée au premier démarrage.

Le script distant est installé avec des droits contrôlés et n’accepte que les opérations nécessaires au backend choisi. La clé privée SSH reste un secret côté application; seule la clé publique est installée dans le compte VPN dédié.

## Fichiers produits

| Chemin | Contenu |
| --- | --- |
| `/etc/ttl-lama/config.yml` | Application, authentification, base, hasher et sécurité |
| `/etc/ttl-lama/backend_config.yml` | Backends, interfaces et profils |
| `/etc/ttl-lama/ssh_config.yml` | Paramètres du transport SSH |
| `/etc/ttl-lama/ssh_known_hosts` | Clé d’hôte VPN vérifiée |
| `.env.example` | Noms des variables d’environnement à configurer |
| `.env` | Valeurs renseignées par l’utilisateur et transmises avec `--env-file`; exclu du dépôt |
| `/run/secrets/` | Secrets fournis sous forme de fichiers, notamment la clé privée SSH |
| `/opt/ttl-lama-vpn/` | Script distant généré pour le backend |

Le questionnaire Python valide les réponses et écrit les fichiers structurés; Bash orchestre les vérifications et affiche les commandes de déploiement sans les exécuter. Les mots de passe OIDC et de base de données sont fournis dans `.env`; le mot de passe initial du compte administrateur est écrit dans le YAML de bootstrap.

## Garde-fous et limites actuelles

- Valider tous les paramètres avant d’afficher les commandes ou de modifier l’hôte VPN.
- Rendre les étapes relançables; sauvegarder les configurations remplacées.
- Vérifier les règles avec `visudo -cf`; ne pas autoriser un `sudo` générique.
- Confirmer explicitement la création/révocation de comptes et la rotation des clés.
- Le backend serveur WireGuard est intégré au scheduler via SSH. La réconciliation complète des pairs a lieu au démarrage du scheduler; seul le traitement des opérations en attente est périodique. OpenVPN reste une option du questionnaire, pas un backend serveur intégré.
