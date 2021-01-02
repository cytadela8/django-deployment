#!/usr/bin/python3
"""
Django Deployment Automation script

This script is designed limit downtime when performing updates on Django
applications. The "deploy" command is designed to perform a
non-destructive update of Django with multiple checks and fallback procedures
designed to revert changes in case of failure. This script also provides a few other
commands for checks and manual reverting to previous code versions.

All commands can be listed by executing `fab --list` after installing
dependencies. You can get more help with `fab --list COMMAND_NAME`.

IMPORTANT: This scripts makes following assumptions about the production
environment:
- user "app" manages the Django App code and config
- user "admin" has sudo access
- configuration variables in fabric.yml are set correctly
- scripts:
    - all return a non zero exit code on failure
    - ~app/scripts/backup_database.sh - backups the Django App database
    - ~app/scripts/start_maintenance.sh - performs pre app update tasks
    - ~app/scripts/stop_maintenance.sh - performs post app update tasks (run also when update failed, but start_maintanance was run before)
- Systemd django.service manages the Django App supervisord
- symlinks:
    - ~app/django-current, ~app/django-previous, ~app/django-working,
        ~app/django-previous-working - are valid symlinks to the Django App Versions
        directories (see below for definition of the Django App version directory)
    - Django STATIC_ROOT points (possibly via symlink) to
        ~app/django-current/static
    - ~app/venv is a symlink to ~app/django-current/venv
    - ~app/django is a symlink to ~app/django-current/code
    - ~app/deployment is an the Django App deployment directory
    - settings*, supervisord*, wsgi*, manage.py, django in ~app/deployment are
        symlinks to respective files in ~app/django-current/config
- the Django App version directory contents:
    - code - the Django App code git repository
    - config - the Django App configuration files git repository
    - static - Django STATIC_ROOT files
    - venv - Python virtualenv with the Django App dependencies installed
"""
from fabric import task
from invoke import Collection
import invoke.exceptions
import datetime

from django_connection import DjangoConnection
from utils import Fallback, handle_exceptions
from logger import logger

# Hide a deprecation warning caused by Paramiko code
import warnings
warnings.filterwarnings("ignore", module="paramiko.kex_ecdh_nist")


ns = Collection()
ns.configure({
    'code_subdir': "code",
    'config_subdir': "config",
    'venv_subdir': "venv",
    'static_subdir': "static",
    'deployment_dir': "~/deployment",
    'current_venv_dir': "~/venv",
    'current_code': "~/django",
    'current_config': "~/django-current/config/",
    'current_main': "~/django-current",
    'previous_main': "~/django-previous",
    'current_working': "~/django-working",
    'previous_working': "~/django-previous-working",
    'systemd_service': "app",
    'maintenance_start_script': "~/scripts/start_maintenance.sh",
    'maintenance_stop_script': "~/scripts/stop_maintenance.sh",
    'backup_script': "~/script/backup_database.sh",
    'admin_username': "admin",
    'app_username': "app",
    'perform_install_script': "~/django-current/config/perform_install.sh",
})


@task
@handle_exceptions
def check_uncommited(c):
    """
    Check for uncommited or unpushed changes
    """
    s = DjangoConnection.get_instance(c.config)
    try:
        s.check_for_uncommited_changes()
        print("No uncommited or unpushed changes")
    except invoke.exceptions.UnexpectedExit as e:
        logger.error("Found uncommited changes!")
        raise Fallback(e)
    except Exception as e:
        logger.error("Exception in check for uncommited changes")
        raise Fallback(e)
ns.add_task(check_uncommited)


@task(help={'code': "Code commit hash to use",
            'config': "Config commit hash to use"})
def create_version(c, code, config):
    """
    Create version

    Creates Django App version given code and config versions
    """
    s = DjangoConnection.get_instance(c.config)

    code_commit = code
    config_commit = config
    new_path = "django" \
               + "-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") \
               + "-" + code_commit[:6] \
               + "-" + config_commit[:6]

    try:
        s.start_maintenance()
        s.prepare_version(new_path, code_commit, config_commit)
    except Exception as e:
        logger.info("Code generation failed!")
        raise Fallback(e)
    finally:
        s.stop_maintenance()

    return new_path
ns.add_task(create_version)


@task(help={'name': "Instance name / path",
            'migrate': "Perform Django migrations (defaults to yes)",
            'collect-static': "Collect Django static files (defaults to no)",
            'clear_cache': "Clear Django cache (defaults to yes)",
            'compress': "Perform django-compress (defaults to no)"})
@handle_exceptions
def change_version(c, name, migrate=True, collect_static=False,
                   clear_cache=True, compress=False):
    """
    Change running version
    """
    s = DjangoConnection.get_instance(c.config)
    if name not in s.list_versions():
        raise Exception("Version {} not found. Name of a version has to be a "
                        "path to a Django App version folder eg. "
                        "django-20190505-1800-abcdef-fedcba. Never a path to "
                        "a symlink!".format(name))

    s.stop_django()
    s.change_codebase(name)

    if migrate:
        s.django_migrations()
    if collect_static:
        s.django_collect_static()
    if clear_cache:
        s.django_clear_cache()
    if compress:
        s.django_compress()

    s.start_django()

    s.check_app_works()
    s.mark_working(name)
ns.add_task(change_version)


@task
@handle_exceptions
def restart_django(c):
    """
    Restart currently running Django App version
    """
    s = DjangoConnection.get_instance(c.config)
    s.stop_django()
    s.start_django()
ns.add_task(restart_django)


@task(help={'code': "Code commit hash to use",
            'config': "Config commit hash to use",
            'check-hotfixes': "Check for uncommited or unpushed changes ("
                              "defaults to yes)",
            'backup': "Backup database (defaults to yes)"})
@handle_exceptions
def deploy(c, code, config, check_hotfixes=True, backup=True):
    """
    the Django App deployment

    This task:
    1. Assures all changes on production were pushed to repositories
    2. Downloads given code and config version
    3. Stops the Django App
    4. Makes database backup
    5. Applies django upgrade functions (migrations, etc.)
    6. Starts the Django App
    """
    try:
        s = DjangoConnection.get_instance(c.config)
        beginning_version = s.get_current_version()
        if check_hotfixes:
            check_uncommited(c)

        new_path = create_version(c, code, config)
    except Exception as e:
        logger.error("Exception caught. Running Django App was not affected or "
                     "\"touched\".")
        raise Fallback(e)

    # END OF SAFE TO FAIL CODE

    try:
        s.stop_django()
        s.change_codebase(new_path)

        s.django_check_manage()
        if backup:
            s.backup_database()
        s.django_perform_install()

    except Exception as e:
        logger.error("Exception caught")

        try:
            current_version = s.get_current_version()
        except Exception:
            current_version = ""
        if current_version != beginning_version:
            s.change_codebase(beginning_version)
        assert s.get_current_version() == beginning_version

        s.start_django()
        s.check_app_works()
        raise Fallback(e)

    # END OF CODE WITH FALLBACK

    # run manage.py migrate
    # after this, we cannot automatically restore the Django App
    s.django_migrations()

    s.start_django()
    s.check_app_works()
    s.mark_working(new_path)
ns.add_task(deploy)

@task
@handle_exceptions
def list_versions(c):
    """
    List available versions
    """
    s = DjangoConnection.get_instance(c.config)
    interestring_versions = [
        (s.get_current_version(), 'current'),
        (s.get_previous_version(), 'previous'),
        (s.get_working_version(), 'working'),
        (s.get_previous_working_version(), 'working-old'),
    ]
    print("Existing versions: (date-time-code-config)")
    for version in s.list_versions():
        print(version, end=" ")
        for (name, tag) in interestring_versions:
            if name == version:
                print(tag, end=" ")
        print()
ns.add_task(list_versions)


@task(aliases=['delete'],
      help={'name': "Instance name / path"})
@handle_exceptions
def delete_version(c, name):
    """
    Delete a version
    """
    s = DjangoConnection.get_instance(c.config)
    s.delete_version(name)
    print("Done!")
ns.add_task(delete_version)


@task(help={'to-keep': "Number of versions to keep"})
@handle_exceptions
def delete_old_versions(c, to_keep=10):
    """
    Delete old versions
    """
    s = DjangoConnection.get_instance(c.config)
    versions = s.list_versions()
    if len(versions) <= to_keep:
        print("Nothing to do")
    else:
        s.delete_versions(versions[:-to_keep])
ns.add_task(delete_old_versions)