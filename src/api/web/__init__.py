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

from auth.manager import AuthManager
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
			"profiles": "Available access profiles",
		},
		"section_copy": {
			"devices": "Manage the devices associated with your account.",
			"leases": "Review and manage your time-limited network access.",
			"profiles": "Review the access profiles available to you.",
		},
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
			"profiles": "Profils d’accès disponibles",
		},
		"section_copy": {
			"devices": "Gérez les appareils associés à votre compte.",
			"leases": "Consultez et gérez vos accès réseau à durée limitée.",
			"profiles": "Consultez les profils d’accès disponibles pour votre compte.",
		},
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
    manager = cast(
        AuthManager | None,
        current_app.extensions.get("auth_manager"),
    )
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
    manager = cast(AuthManager | None, current_app.extensions.get("auth_manager"))
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
    """Display a user section pending implementation.

    :param section_name: Name of the user section to display.
    :type section_name: str
    :return: Rendered section page.
    :rtype: str
    """
    if section_name not in {"devices", "leases", "profiles"}:
        abort(404)

    language = _selected_language()
    text = cast(dict[str, Any], TEXT[language])
    return _render_page(
        "section.html",
        "fragments/section.html",
        section=section_name,
        title=text["section_title"][section_name],
        description=text["section_copy"][section_name],
    )
