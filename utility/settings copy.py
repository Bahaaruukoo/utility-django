import os
from pathlib import Path

from django.contrib.messages import constants as messages

BASE_DIR = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------------------
# SECURITY
# ------------------------------------------------------------------------------
SECRET_KEY = 'django-insecure-cj7i1@@2uqn_hytapgcqx=(=3gg*2xfd8b+p-w+1e2(&l*4b$r'
DEBUG = True
ALLOWED_HOSTS = []


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
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    'allauth.account.middleware.AccountMiddleware',
    "core.middleware.TenantAccessMiddleware",
    #"core.middleware.TenantPermissionMiddleware",
    "core.middleware.BranchMiddleware",
    "core.middleware.NoTenantUserOnPublicAdminMiddleware",
    "core.session.session_meta_middleware.SessionMetaMiddleware",
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

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': 'utility2',
        'USER': 'postgres',
        'PASSWORD': 'ejokoo123',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

SESSION_ENGINE = "django.contrib.sessions.backends.db"


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

# ------------------------------------------------------------------------------
# PASSWORD VALIDATION
# ------------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
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

DOMAIN = 'localhost'
PORT = ':8000'

# ------------------------------------------------------------------------------
# DEFAULTS
# ------------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'



LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'system.log')

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
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(BASE_DIR, "logs/system.log"),
            "maxBytes": 1024 * 1024 * 10,
            "backupCount": 5,
            "formatter": "standard",
            "filters": ["context"],
        }
    },

    "loggers": {
        "app": {
            "handlers": ["file"],
            "level": "INFO",
            "propagate": False,
        }
    }
}

