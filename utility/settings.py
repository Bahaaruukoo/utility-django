import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.contrib.messages import constants as messages
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------------------
# SECURITY
# ------------------------------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", get_random_secret_key())
#'django-insecure-cj7i1@@2uqn_hytapgcqx=(=3gg*2xfd8b+p-w+1e2(&l*4b$r'
DEBUG = os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS",".utilityko.com").split(",") # 
DEVELOPMENT_MODE = os.getenv("DEVELOPMENT_MODE", "False") == "True"

# ------------------------------------------------------------------------------
# APPLICATIONS
# ------------------------------------------------------------------------------

SHARED_APPS = [
    # django-tenants
    'django_tenants',
    'tenant_manager',

    # Django core (shared)
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'core',
    # Third-party (shared)
    "allauth_ui",
    'allauth',
    'allauth.account',


    'widget_tweaks',
    'slippers',
    'rest_framework',
    "axes",
]

TENANT_APPS = [
    # Tenant-isolated apps
    'tenant_utils',
    'customers',
    'bills',
    'payments',
    'reports',
    'portal',
    'rangefilter',
]

INSTALLED_APPS = SHARED_APPS + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]


# ------------------------------------------------------------------------------
# MIDDLEWARE
# ------------------------------------------------------------------------------

MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',
    'core.middleware.PublicAuthSchemaMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'core.middleware.SessionBindingMiddleware',

    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    "axes.middleware.AxesMiddleware",

    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",

    'allauth.account.middleware.AccountMiddleware',
    "core.middleware.TenantAccessMiddleware",
    #"core.middleware.TenantPermissionMiddleware",
    "core.middleware.BranchMiddleware",
    "core.middleware.NoTenantUserOnPublicAdminMiddleware",
    "core.session.session_meta_middleware.SessionMetaMiddleware",
    'core.middleware.SessionBindingCookieMiddleware',

    "core.middleware.RequestLoggingMiddleware",

]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "tenant_utils.api.authentication.APIKeyAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ), 
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=12),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ------------------------------------------------------------------------------
# URLS / WSGI
# ------------------------------------------------------------------------------
ROOT_URLCONF = 'utility.urls'
PUBLIC_SCHEMA_URLCONF = 'utility.urls_public'
WSGI_APPLICATION = 'utility.wsgi.application'


MESSAGE_TAGS = {messages.ERROR: 'danger',}

# ------------------------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------------------------

if DEVELOPMENT_MODE is True:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.config(
            default=os.environ.get("DATABASE_URL")
        )
    }
    DATABASES["default"]["ENGINE"] = "django_tenants.postgresql_backend"

elif len(sys.argv) > 0 and sys.argv[1] != 'collectstatic':
    if os.getenv("DATABASE_URL", None) is None:
        raise Exception("DATABASE_URL environment variable not defined")
    DATABASES = {
        "default": dj_database_url.config(
            default=os.environ.get("DATABASE_URL")     
        )
    }
    DATABASES["default"]["ENGINE"] = "django_tenants.postgresql_backend"
    
DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

SESSION_ENGINE = "django.contrib.sessions.backends.db"

if DEBUG:
    BINDING_COOKIE_NAME = "binding_token"
else:
    BINDING_COOKIE_NAME = "__Host-binding_token"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_SAVE_EVERY_REQUEST = False
# ------------------------------------------------------------------------------
# TENANT CONFIG
# ------------------------------------------------------------------------------

TENANT_MODEL = "tenant_manager.Tenant"
TENANT_DOMAIN_MODEL = "tenant_manager.Domain"

#SHOW_PUBLIC_IF_NO_TENANT_FOUND = True
#TENANT_NOT_FOUND_EXCEPTION = True


# ------------------------------------------------------------------------------
# AUTHENTICATION
# ------------------------------------------------------------------------------

AUTH_USER_MODEL = "core.CustomUser"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",

    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
    "core.auth_backends.TenantAwareBackend",   # keep if you need tenant rules
]


LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'


# ------------------------------------------------------------------------------
# ALLAUTH
# ------------------------------------------------------------------------------


ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = [ 'email', 'password1', 'password2' ]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True
#ACCOUNT_ALLOW_REGISTRATION = False
#ACCOUNT_FORMS = {    "login": "core.forms.TenantLoginForm",}

#ACCOUNT_SIGNUP_FORM_CLASS = 'core.forms.CustomSignupForm'
ACCOUNT_ADAPTER = 'core.adapters.NoPublicSignupAdapter'

ALLAUTH_UI_THEME = 'light'  # or 'dark'
#ACCOUNT_RATE_LIMITS = {"login_failed": "5/5m/ip", } # limit failed logins to 5 per 5 minutes per IP

# ------------------------------------------------------------------------------
# PASSWORD VALIDATION
# ------------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     "OPTIONS": {
            "min_length": 12,
        },
     },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ------------------------------------------------------------------------------
# TEMPLATES
# ------------------------------------------------------------------------------

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


# ------------------------------------------------------------------------------
# I18N / TZ
# ------------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# ------------------------------------------------------------------------------
# STATIC / MEDIA
# ------------------------------------------------------------------------------

STATIC_URL = '/static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DOMAIN = 'localhost'
PORT = ':8000'

CSRF_FAILURE_VIEW = "portal.views.csrf_failure"

# ------------------------------------------------------------------------------
# DEFAULTS
# ------------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
#EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

#EMAIL_HOST_USER = 'email.utilityko@gmail.com'
#EMAIL_HOST_PASSWORD = 'ydgx drgm irxp umrn'
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


# Enable Axes
AXES_ENABLED = True

# Lock after 5 failed attempts
AXES_FAILURE_LIMIT = 5

# Lock for 15 minutes
AXES_COOLOFF_TIME = timedelta(minutes=15)

# Do not restart the timer during lockout
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False

# Clear failures after successful login
AXES_RESET_ON_SUCCESS = True

# allauth login field
AXES_USERNAME_FORM_FIELD = "login"

# Custom username extractor
AXES_USERNAME_CALLABLE = "core.axes.get_username"

# Lock by email + IP
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]

# Keep audit trail
AXES_ENABLE_ACCESS_FAILURE_LOG = True

# Return HTTP 429
AXES_HTTP_RESPONSE_CODE = 429

# Optional
AXES_LOCKOUT_TEMPLATE = "axes/lockout.html"



LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'system.log')


LOG_TO_FILE = os.environ.get("LOG_TO_FILE", "0") == "0"

LOG_DIR = Path(BASE_DIR) / "logs"
if LOG_TO_FILE:
    LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "filters": {
        "context": {
            "()": "core.logging_filters.ContextFilter",
        }
    },

    "formatters": {
        "standard": {
            "format": "[{asctime}] {levelname} tenant={tenant} branch={branch} user={user} request={request_id} {message}",
            "style": "{",
        }
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["context"],
        }
    },

    "loggers": {
        "app": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        }
    }
}


