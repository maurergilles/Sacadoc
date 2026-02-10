import os

import pytest
from django.conf.global_settings import SESSION_COOKIE_NAME
from playwright.sync_api import Page

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for tests."""
    return {
        **browser_context_args,
        "ignore_https_errors": True,
        "locale": "fr-FR",
        "timezone_id": "Europe/Paris",
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Configure browser launch arguments."""
    return {
        **browser_type_launch_args,
        "headless": False,
    }

@pytest.fixture(scope="session")
def django_db_setup():
    import subprocess
    from django.conf import settings
    db_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
    test_db_path = os.path.join(settings.BASE_DIR, 'test.sqlite3')

    subprocess.run(
        f"sqlite3 {db_path} .schema | sqlite3 {test_db_path}",
        shell=True,
        check=True
    )
    settings.DATABASES['default']['NAME'] = test_db_path


@pytest.fixture
def auto_login_user(db, client, live_server, page: Page):
    def make_auto_login(user):
        client.force_login(user)
        session_cookie = client.cookies[SESSION_COOKIE_NAME]

        page.context.add_cookies([{
            'name': SESSION_COOKIE_NAME,
            'value': session_cookie.value,
            'domain': live_server.url.split("//")[1].split(":")[0],
            'path': "/"
        }])

        return page

    return make_auto_login