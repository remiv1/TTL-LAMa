"""API web package.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import cast, Any

from flask import (
	Blueprint,
	abort,
	current_app,
	g,
	redirect,
	render_template,
	request,
	url_for,
)
from werkzeug.wrappers import Response as WerkzeugResponse

from api.database import get_session
from api.common.repositories import (
	DeviceRepository,
	LeaseRepository,
	ProfileRepository,
)
from api.common.repositories.leases import lease_status
from auth.manager import get_optional_manager
from auth.models import UnifiedUser

LANGUAGE_COOKIE = "ttl_lama_language"
SUPPORTED_LANGUAGES = {"en", "fr"}
TEXT = {
	"en": {
		"brand": "TTL-LAMa",
		"skip_content": "Skip to content",
		"menu": "Open navigation menu",
		"navigation": "Main navigation",
		"authentication": "Authentication",
		"sign_in": "Sign in",
		"account": "Account and session",
		"sign_out": "Sign out",
		"usage": "Usage",
		"devices": "Devices",
		"leases": "Access leases",
		"profiles": "Access profiles",
		"language": "Language",
		"footer": "Temporary network access, with an end built in.",
		"eyebrow": "Time-To-Live Lease Access Manager",
		"hero_title": "Temporary access. Automatic revocation.",
		"hero_copy": "Grant access for a defined time, then let its lifecycle take care of " \
			"the rest.",
		"logo_placeholder": "Temporary logo placeholder",
		"intro_title": "Access should have an end date.",
		"intro_copy": "TTL-LAMa manages time-limited access leases for private networks. Operators " \
			"define the policy; each lease expires or can be revoked when it is no longer needed.",
		"principles_title": "Designed around the lease lifecycle",
		"principle_one_title": "Time-bounded",
		"principle_one_copy": "Every authorization is issued with a defined lifetime.",
		"principle_two_title": "Operator-controlled",
		"principle_two_copy": "Access profiles and infrastructure policy remain with the operator.",
		"principle_three_title": "Automatically withdrawn",
		"principle_three_copy": "Expired or revoked leases no longer grant access.",
		"login_title": "Sign in",
		"login_copy": "Use your configured TTL-LAMa account.",
		"username": "Username",
		"password": "Password",
		"invalid_login": "The username or password is not valid.",
		"submit_login": "Continue",
		"account_title": "Account and session",
		"session_active": "Your session is active.",
		"user_id": "User ID",
		"email": "Email",
		"not_provided": "Not provided",
		"role": "Role",
		"administrator": "Administrator",
		"user": "User",
		"pending": "This area is not available yet. Its operations will appear here when the " \
			"service is implemented.",
		"not_available": "Not available yet",
		"section_title": {
			"devices": "Your devices",
			"leases": "Your access leases",
			"profiles": "Your assigned access profiles",
		},
		"section_copy": {
			"devices": "Manage the devices associated with your account.",
			"leases": "Review and manage your time-limited network access.",
			"profiles": "Review the access profiles assigned to your account.",
		},
		"device_name": "Device name",
		"add_device": "Add device",
		"device_details": "Device details",
		"device_identifier": "Device ID",
		"device_created": "Created",
		"public_key": "Public key",
		"generate_keys": "Generate a key pair",
		"private_key": "Private key",
		"copy_private_key": "Copy private key",
		"create_device": "Create device",
		"close": "Close",
		"device_success": "Device created.",
		"device_error": "The device could not be created.",
		"delete_device": "Revoke device",
		"delete_device_title": "Revoke this device?",
		"delete_device_notice": "This will revoke the device and all of its active access leases." +
            "Device history will be retained.",
		"confirm_delete_device": "Revoke device",
		"cancel": "Cancel",
		"delete_device_success": "Device revoked.",
		"delete_device_error": "The device could not be revoked.",
		"keygen_error": "Key generation is not supported by this browser.",
		"copied_private_key": "Private key copied.",
		"copy_private_key_error": "Copy failed. Select and copy the key manually.",
		"private_key_notice": "Save this private key now. It is generated in your " +
		"browser and is never sent to the server.",
		"empty_devices": "No devices yet.",
		"profile_id": "Profile",
		"default_duration": "Default duration",
		"maximum_duration": "Maximum duration",
		"allowed_networks": "Allowed networks",
		"empty_profiles": "No access profiles are assigned to your account yet.",
		"policy_unavailable": "No access policy is currently associated with this profile.",
		"add_lease": "Request access",
		"create_lease_title": "Request network access",
		"create_lease": "Create lease",
		"lease_success": "Access lease created.",
		"lease_error": "The access lease could not be created.",
		"lease_details": "Lease details",
		"lease_identifier": "Lease ID",
		"lease_device": "Device",
		"lease_profile": "Access profile",
		"lease_status": "Status",
		"lease_created": "Created",
		"lease_ends": "Access ends",
		"lease_revoked_at": "Revoked at",
		"lease_duration": "Requested duration",
		"duration_optional": "Optional duration",
		"duration_help": "Leave blank to use the profile default. Use d, h, m, or s units.",
		"lease_default": "Default duration",
		"lease_maximum": "Maximum duration",
		"lease_networks": "Allowed networks",
		"empty_current_leases": "No active or expired leases.",
		"empty_leases": "No access leases yet.",
		"empty_lease_devices": "Add an active device before requesting access.",
		"empty_lease_profiles": "No eligible assigned access profiles are available.",
		"revoked_leases": "Revoked leases",
		"active_status": "Active",
		"pending_status": "Pending",
		"failed_status": "Failed",
		"expired_status": "Expired",
		"revoked_status": "Revoked",
		"revoke_lease": "Revoke lease",
		"revoke_lease_title": "Revoke this access lease?",
		"revoke_lease_notice": "Access will end immediately. The lease history will be retained.",
		"confirm_revoke_lease": "Revoke lease",
		"lease_revoke_success": "Access lease revoked.",
		"lease_revoke_error": "The access lease could not be revoked.",
	},
	"fr": {
		"brand": "TTL-LAMa",
		"skip_content": "Aller au contenu",
		"menu": "Ouvrir le menu de navigation",
		"navigation": "Navigation principale",
		"authentication": "Authentification",
		"sign_in": "Se connecter",
		"account": "Compte et session",
		"sign_out": "Se déconnecter",
		"usage": "Utilisation",
		"devices": "Appareils",
		"leases": "Baux d’accès",
		"profiles": "Profils d’accès",
		"language": "Langue",
		"footer": "Un accès réseau temporaire, avec une fin prévue.",
		"eyebrow": "Gestionnaire de baux d’accès à durée limitée",
		"hero_title": "Accès temporaire. Révocation automatique.",
		"hero_copy": "Accordez un accès pour une durée définie, puis laissez son cycle de vie " \
			"suivre son cours.",
		"logo_placeholder": "Emplacement provisoire du logo",
		"intro_title": "Tout accès devrait avoir une date de fin.",
		"intro_copy": "TTL-LAMa gère des baux d’accès temporaires aux réseaux privés. " \
            "L’opérateur définit la politique; chaque bail expire ou peut être révoqué dès qu’il " \
            "n’est plus nécessaire.",
		"principles_title": "Un cycle de vie au cœur du modèle",
		"principle_one_title": "À durée limitée",
		"principle_one_copy": "Chaque autorisation est accordée pour une durée définie.",
		"principle_two_title": "Sous le contrôle de l’opérateur",
		"principle_two_copy": "Les profils d’accès et la politique d’infrastructure restent " \
			"sous le contrôle de l’opérateur.",
		"principle_three_title": "Retiré automatiquement",
		"principle_three_copy": "Un bail expiré ou révoqué ne donne plus accès au réseau.",
		"login_title": "Se connecter",
		"login_copy": "Utilisez le compte TTL-LAMa configuré.",
		"username": "Nom d’utilisateur",
		"password": "Mot de passe",
		"invalid_login": "Le nom d’utilisateur ou le mot de passe est invalide.",
		"submit_login": "Continuer",
		"account_title": "Compte et session",
		"session_active": "Votre session est active.",
		"user_id": "Identifiant utilisateur",
		"email": "Adresse e-mail",
		"not_provided": "Non renseignée",
		"role": "Rôle",
		"administrator": "Administrateur",
		"user": "Utilisateur",
		"pending": "Cette rubrique n’est pas encore disponible. Ses opérations apparaîtront ici " \
			"lorsque le service sera implémenté.",
		"not_available": "Pas encore disponible",
		"section_title": {
			"devices": "Vos appareils",
			"leases": "Vos baux d’accès",
			"profiles": "Vos profils d’accès attribués",
		},
		"section_copy": {
			"devices": "Gérez les appareils associés à votre compte.",
			"leases": "Consultez et gérez vos accès réseau à durée limitée.",
			"profiles": "Consultez les profils d’accès attribués à votre compte.",
		},
		"device_name": "Nom de l’appareil",
		"add_device": "Ajouter un appareil",
		"device_details": "Détails de l’appareil",
		"device_identifier": "Identifiant de l’appareil",
		"device_created": "Créé le",
		"public_key": "Clé publique",
		"generate_keys": "Générer une paire de clés",
		"private_key": "Clé privée",
		"copy_private_key": "Copier la clé privée",
		"create_device": "Créer l’appareil",
		"close": "Fermer",
		"device_success": "L’appareil a été créé.",
		"device_error": "La création de l’appareil a échoué.",
		"delete_device": "Révoquer l’appareil",
		"delete_device_title": "Révoquer cet appareil ?",
		"delete_device_notice": "Cette action révoquera l’appareil ainsi que tous ses " +
			"baux d’accès actifs. L’historique de l’appareil sera conservé.",
		"confirm_delete_device": "Révoquer l’appareil",
		"cancel": "Annuler",
		"delete_device_success": "L’appareil a été révoqué.",
		"delete_device_error": "La révocation de l’appareil a échoué.",
		"keygen_error": "Ce navigateur ne permet pas de générer les clés requises.",
		"copied_private_key": "Clé privée copiée.",
		"copy_private_key_error": "Copie impossible. Sélectionnez et copiez la clé manuellement.",
		"private_key_notice": "Enregistrez cette clé privée maintenant. Elle est générée dans "
		"votre navigateur et n’est jamais envoyée au serveur.",
		"empty_devices": "Aucun appareil pour le moment.",
		"profile_id": "Profil",
		"default_duration": "Durée par défaut",
		"maximum_duration": "Durée maximale",
		"allowed_networks": "Réseaux autorisés",
		"empty_profiles": "Aucun profil d’accès n’est attribué à votre compte pour le moment.",
		"policy_unavailable": "Aucune politique d’accès n’est actuellement associée à ce profil.",
		"add_lease": "Demander un accès",
		"create_lease_title": "Demander un accès réseau",
		"create_lease": "Créer le bail",
		"lease_success": "Le bail d’accès a été créé.",
		"lease_error": "La création du bail d’accès a échoué.",
		"lease_details": "Détails du bail",
		"lease_identifier": "Identifiant du bail",
		"lease_device": "Appareil",
		"lease_profile": "Profil d’accès",
		"lease_status": "État",
		"lease_created": "Créé le",
		"lease_ends": "Fin de l’accès",
		"lease_revoked_at": "Révoqué le",
		"lease_duration": "Durée demandée",
		"duration_optional": "Durée facultative",
		"duration_help": "Laissez vide pour utiliser la durée par défaut du profil. " +
        "Unités : d, h, m ou s.",
		"lease_default": "Durée par défaut",
		"lease_maximum": "Durée maximale",
		"lease_networks": "Réseaux autorisés",
		"empty_current_leases": "Aucun bail actif ou expiré.",
		"empty_leases": "Aucun bail d’accès pour le moment.",
		"empty_lease_devices": "Ajoutez un appareil actif avant de demander un accès.",
		"empty_lease_profiles": "Aucun profil d’accès attribué et utilisable n’est disponible.",
		"revoked_leases": "Baux révoqués",
		"active_status": "Actif",
		"pending_status": "En attente",
		"failed_status": "Échec",
		"expired_status": "Expiré",
		"revoked_status": "Révoqué",
		"revoke_lease": "Révoquer le bail",
		"revoke_lease_title": "Révoquer ce bail d’accès ?",
		"revoke_lease_notice": "L’accès prendra fin immédiatement. L’historique du bail sera conservé.",
		"confirm_revoke_lease": "Révoquer le bail",
		"lease_revoke_success": "Le bail d’accès a été révoqué.",
		"lease_revoke_error": "La révocation du bail d’accès a échoué.",
	},
}

web = Blueprint(
	"web",
	__name__,
	template_folder="templates",
	static_folder="static",
	static_url_path="/web/static",
)


def _selected_language() -> str:
    language = request.cookies.get(LANGUAGE_COOKIE, "en")
    return language if language in SUPPORTED_LANGUAGES else "en"


def _render_page(
    template: str,
    fragment_template: str,
    **context: object,
) -> str:
    language = _selected_language()
    selected_template = (
        fragment_template
        if request.headers.get("HX-Request") == "true"
        else template
    )
    return render_template(
        selected_template,
        language=language,
        text=TEXT[language],
        **context,
    )


@web.before_request
def load_current_user() -> None:
    """Charge curent user in the global context.

    :return: None
    :rtype: None
    """
    manager = get_optional_manager()
    cookie_name = cast(str, current_app.config["AUTH_COOKIE_NAME"])
    token = request.cookies.get(cookie_name)
    g.current_user = manager.get_current_user(token) if manager and token else None


@web.get("/")
def index() -> str:
    """Load the presentation page.

	:return: Rendered presentation page.
	:rtype: str
    """
    return _render_page("home.html", "fragments/home.html")


@web.get("/login")
def login() -> WerkzeugResponse | str:
    """Display the internal login form.

    :return: Rendered login page or redirect response.
    :rtype: WerkzeugResponse | str
    """
    config = cast(dict[str, object], current_app.config)
    if config.get("AUTH_MODE") != "internal":
        return redirect(url_for("auth.login"))
    return _render_page(
        "login.html",
        "fragments/login.html",
        error=request.args.get("error"),
    )


@web.get("/account")
def account() -> WerkzeugResponse | str:
    """Display user information and session status.

    Affiche les informations de l’utilisateur et l’état de sa session.

    :return: Rendered account page or redirect response.
    :rtype: WerkzeugResponse | str
    """
    user = cast(UnifiedUser | None, g.current_user)
    if user is None:
        return redirect(url_for("auth.login"))
    return _render_page("account.html", "fragments/account.html", user=user)


@web.post("/logout")
def logout():
    """Revoke the current session and delete its cookie.

    :return: Redirect response to the index page.
    :rtype: Response
    """
    cookie_name = cast(str, current_app.config["AUTH_COOKIE_NAME"])
    token = request.cookies.get(cookie_name)
    manager = get_optional_manager()
    if manager is not None and token:
        manager.logout(token)

    response = redirect(url_for("web.index"), code=303)
    response.delete_cookie(
        key=cookie_name,
        path=cast(str, current_app.config["SESSION_COOKIE_PATH"]),
        secure=cast(bool, current_app.config["SESSION_COOKIE_SECURE"]),
        httponly=cast(bool, current_app.config["SESSION_COOKIE_HTTPONLY"]),
        samesite=cast(str, current_app.config["SESSION_COOKIE_SAMESITE"]),
    )
    return response


@web.post("/language")
def set_language() -> WerkzeugResponse:
    """Memorize the language and return only to a local URL.

    Mémorise la langue et revient uniquement vers une URL locale.

    :return: Redirect response to the target URL.
    :rtype: WerkzeugResponse
    """
    language = request.form.get("language", "en")
    if language not in SUPPORTED_LANGUAGES:
        language = "en"

    target = request.form.get("next", "/")
    if (
        not target.startswith("/")
        or target.startswith("//")
        or "\\" in target
    ):
        target = "/"
    response = redirect(target, code=303)
    response.set_cookie(
        key=LANGUAGE_COOKIE,
        value=language,
        max_age=31536000,
        httponly=True,
        secure=cast(bool, current_app.config["SESSION_COOKIE_SECURE"]),
        samesite="Lax",
        path="/",
    )
    return response


@web.get("/<section_name>")
def show_section(section_name: str) -> str:
    """Display a user section, including the user's devices or assigned profiles.

    :param section_name: Name of the user section.
    :type section_name: str
    :return: Rendered section page.
    :rtype: str
    """
    if section_name not in {"devices", "leases", "profiles"}:
        abort(404)

    language = _selected_language()
    text = cast(dict[str, Any], TEXT[language])
    user = cast(UnifiedUser | None, g.current_user)
    devices = (
        [
            device
            for device in DeviceRepository(get_session()).find(user=str(user.id))
            if device.revoked_at is None
        ]
        if section_name in {"devices", "leases"} and user is not None
        else []
	)
    profiles: list[dict[str, object]] = []
    lease_profiles: list[dict[str, object]] = []
    current_leases: list[dict[str, object]] = []
    revoked_leases: list[dict[str, object]] = []
    if section_name == "profiles" and user is not None:
        repository = ProfileRepository(get_session())
        profiles = [
            {"profile": profile, "policy": repository.policy(profile)}
            for profile in repository.find(user=str(user.id))
        ]
    if section_name == "leases" and user is not None:
        profile_repository = ProfileRepository(get_session())
        lease_profiles = [
            {"profile": profile, "policy": policy}
            for profile in profile_repository.find(user=str(user.id))
            if profile.revoked_at is None
            and (policy := profile_repository.policy(profile)) is not None
        ]
        leases = sorted(
            LeaseRepository(get_session()).find(user=str(user.id)),
            key=lambda lease: lease.created_at,
            reverse=True,
        )
        for lease in leases:
            item: dict[str, object] = {
                "lease": lease,
                "status": lease_status(lease),
                "device": lease.device,
                "profile": lease.profile,
            }
            if item["status"] == "revoked":
                revoked_leases.append(item)
            else:
                current_leases.append(item)
    return _render_page(
        "section.html",
        "fragments/section.html",
        section=section_name,
        title=text["section_title"][section_name],
        description=text["section_copy"][section_name],
        devices=devices,
        profiles=profiles,
        lease_profiles=lease_profiles,
        current_leases=current_leases,
        revoked_leases=revoked_leases,
    )
