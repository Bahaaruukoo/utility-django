from allauth.account.app_settings import LoginMethod


def get_username(request, credentials):
    if not credentials:
        return None

    return (
        credentials.get("login")
        or credentials.get("email")
        or credentials.get(LoginMethod.EMAIL)
        or request.POST.get("login")
    )