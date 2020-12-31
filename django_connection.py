import time

from fabric import Connection
from shlex import quote as q
import os
import requests

from logger import logger


class DjangoConnection:
    CODE_SUBDIR = "code"
    CONFIG_SUBDIR = "config"
    VENV_SUBDIR = "venv"
    STATIC_SUBDIR = "static"
    DEPLOYMENT_DIR = "~/deployment"
    CURRENT_VENV_DIR = "~/venv"
    CURRENT_CODE = "~/django"
    CURRENT_CONFIG = "~/django-current/config/"
    CURRENT_MAIN = "~/django-current"
    PREVIOUS_MAIN = "~/django-previous"
    CURRENT_WORKING = "~/django-working"
    PREVIOUS_WORKING = "~/django-previous-working"
    SYSTEMD_SERVICE = "django"
    MAINTENANCE_START_SCRIPT = "~/scripts/start_maintenance.sh"
    MAINTENANCE_STOP_SCRIPT = "~/scripts/stop_maintenance.sh"
    BACKUP_SCRIPT = "~/script/backup_database.sh"
    ADMIN_USERNAME = "admin"
    APP_USERNAME = "app"

    def __init__(self, config):
        self.website_url = config.website_url
        self.code_repo_url = config.code_repo_url
        self.config_repo_url = config.config_repo_url
        self.code_branch = config.code_branch
        self.config_branch = config.config_branch

        logger.info("Connecting to {}".format(config.host))
        self.c_adm = Connection(host=config.host, user=self.ADMIN_USERNAME,
                                config=config)
        self.c_usr = Connection(host=config.host, user=self.APP_USERNAME, config=config)
        assert (self.c_adm.run('whoami').stdout.strip() == self.ADMIN_USERNAME)
        assert (self.c_usr.run('whoami').stdout.strip() == self.APP_USERNAME)

    @staticmethod
    def get_instance(config):
        if "s" in config:
            return config.s
        else:
            s = DjangoConnection(config)
            config.s = s
            return s

    def prepare_version(self, path, code_commit, config_commit):
        logger.info("Creating code and config files at {}".format(path))
        self.c_usr.run("mkdir {}".format(path))
        with self.c_usr.cd(path):
            self.c_usr.run("mkdir {}".format(self.STATIC_SUBDIR))
            # Download code
            self._download_repository(self.code_repo_url, self.CODE_SUBDIR,
                                      code_commit, self.code_branch)

            # Download config
            self._download_repository(self.config_repo_url, self.CONFIG_SUBDIR,
                                      config_commit, self.config_branch)

            # Prepare venv
            logger.info("Creating virtualenv")
            self.c_usr.run("virtualenv {}".format(q(self.VENV_SUBDIR)))
            with self.c_usr.prefix("source ~/{}/{}/bin/activate"
                                   .format(path, q(self.VENV_SUBDIR))):
                with self.c_usr.cd(self.CODE_SUBDIR):
                    self.c_usr.run("pip install -r requirements.txt")
                with self.c_usr.cd(self.CONFIG_SUBDIR):
                    self.c_usr.run("pip install -r requirements.txt")
                self.c_usr.run("nodeenv -n 9.9.0 -p")

    def _download_repository(self, url, path, commit, branch):
        logger.info("Downloading repository {} to {}, commit {}"
                     .format(url, path, commit))
        self.c_usr.run("git clone {} {}".format(q(url), q(path)))
        with self.c_usr.cd(path):
            self.c_usr.run("git checkout {}".format(q(commit)))
            self.c_usr.run("git branch -D master")
            self.c_usr.run("git checkout -b {}".format(branch))
            self.c_usr.run(
                "git branch --set-upstream-to=origin/{}".format(branch))

    def stop_maintenance(self):
        logger.info("Stopping maintenance mode")
        self.c_adm.run(self.MAINTENANCE_STOP_SCRIPT)

    def start_maintenance(self):
        logger.info("Starting maintenance mode")
        self.c_adm.run(self.MAINTENANCE_START_SCRIPT)

    def start_django(self):
        self.stop_maintenance()
        logger.info("Starting the App")
        self.c_adm.run("sudo systemctl start -la " + self.SYSTEMD_SERVICE)

    def stop_django(self):
        """
        Stop the Django App, but we don't fail if already stopped
        """
        logger.info("Stopping django")
        self.c_adm.run("sudo systemctl stop -la " + self.SYSTEMD_SERVICE)

    def backup_database(self):
        logger.info("Backing up database")
        filepath = self.c_adm.run(self.BACKUP_SCRIPT).stdout.strip()
        assert int(self.c_adm.run('stat --printf="%s" {}'.format(
            filepath)).stdout) > 100 * 1000  # 100kB

    def check_for_uncommited_changes(self):
        logger.info("Checking for uncommited or unpushed changes")
        self._check_repository(self.CURRENT_CODE)
        self._check_repository(self.CURRENT_CONFIG)

    def _check_repository(self, path):
        with self.c_usr.cd(path):
            # For some reason this is required to refresh git internals
            self.c_usr.run("git status")
            self.c_usr.run("git diff-index --quiet HEAD --")
            # Checked for unpushed commits
            assert "" == self.c_usr.run("git log @{u}..").stdout.strip()

    def change_codebase(self, new_path):
        logger.info("Changing codebase to {}".format(new_path))
        self.c_usr.run("rm -f {}".format(self.PREVIOUS_MAIN))
        self.c_usr.run("mv {} {}".format(self.CURRENT_MAIN, self.PREVIOUS_MAIN))
        self.c_usr.run("ln -s {} {}".format(q(new_path), self.CURRENT_MAIN))

    def change_to_previous_codebase(self):
        self.change_codebase(self.get_previous_version())

    def mark_working(self, new_path):
        if new_path == self.get_working_version():
            return
        self.c_usr.run("rm -f {}".format(self.PREVIOUS_WORKING))
        self.c_usr.run(
            "mv {} {}".format(self.CURRENT_WORKING, self.PREVIOUS_WORKING))
        self.c_usr.run("ln -s {} {}".format(q(new_path), self.CURRENT_WORKING))

    def django_check_manage(self):
        """
        Checks if manage.py succeeds to run without exceptions.

        Such a check finds many common problems including CONFIG_VERSION in
        config not matching INSTALLATION_CONFIG_VERSION in code
        """
        logger.info("Checking manage.py")
        with self.c_usr.prefix(
                "source {}/bin/activate".format(self.CURRENT_VENV_DIR)):
            with self.c_usr.cd(self.DEPLOYMENT_DIR):
                self.c_usr.run("./manage.py")

    def django_migrations(self):
        logger.info("Applying Django migrations")
        with self.c_usr.prefix(
                "source {}/bin/activate".format(self.CURRENT_VENV_DIR)):
            with self.c_usr.cd(self.DEPLOYMENT_DIR):
                self.c_usr.run("./manage.py migrate --no-input")

    def django_collect_static(self):
        logger.info("Collecting Django static files")
        with self.c_usr.prefix(
                "source {}/bin/activate".format(self.CURRENT_VENV_DIR)):
            with self.c_usr.cd(self.DEPLOYMENT_DIR):
                self.c_usr.run("./manage.py collectstatic --no-input")

    def django_clear_cache(self):
        logger.info("Clearing Django cache")
        with self.c_usr.prefix(
                "source {}/bin/activate".format(self.CURRENT_VENV_DIR)):
            with self.c_usr.cd(self.DEPLOYMENT_DIR):
                self.c_usr.run("./manage.py clear_cache")

    def django_compress(self):
        logger.info("Running django-compress")
        with self.c_usr.prefix(
                "source {}/bin/activate".format(self.CURRENT_VENV_DIR)):
            with self.c_usr.cd(self.DEPLOYMENT_DIR):
                self.c_usr.run("./manage.py compress")

    def check_app_works(self):
        logger.info("Testing connection to {}".format(self.website_url))
        r = requests.get(self.website_url)
        count = 0
        # Starting of Django App may take some time.
        while not r.ok and count < 60:
            logger.debug("Waiting for the App start...")
            time.sleep(1)
            r = requests.get(self.website_url)
            count += 1
        assert r.ok

    def get_current_version(self):
        return self._get_link_target_basename(self.CURRENT_MAIN)

    def get_previous_version(self):
        return self._get_link_target_basename(self.PREVIOUS_MAIN)

    def get_working_version(self):
        return self._get_link_target_basename(self.CURRENT_WORKING)

    def get_previous_working_version(self):
        return self._get_link_target_basename(self.PREVIOUS_WORKING)

    def _get_link_target_basename(self, link):
        return os.path.basename(self._get_link_target(link))

    def _get_link_target(self, link):
        return self.c_usr.run("readlink -f {}".format(link)).stdout.strip()

    def delete_version(self, path):
        if path not in self.list_versions():
            raise Exception("Not an available version")
        if os.path.basename(path) in self.get_protected_versions():
            raise Exception("Refusing to delete protected version")
        logger.info("Deleting {}".format(q(path)))
        self.c_usr.run("rm -rf {}".format(q(path)))

    def delete_versions(self, to_delete):
        versions_list = self.list_versions()
        protected_versions = self.get_protected_versions()
        for path in to_delete:
            if path not in versions_list:
                logger.error("Not an available version: {}".format(path))
                continue
            if os.path.basename(path) in protected_versions:
                logger.warning(
                        "Refusing to delete protected version: {}".format(path))
                continue
            logger.info("Deleting {}".format(q(path)))
            self.c_usr.run("rm -rf {}".format(q(path)))

    def get_protected_versions(self):
        return [self.get_current_version(),
                self.get_previous_version(),
                self.get_working_version(),
                self.get_previous_working_version(),
                ]

    def list_versions(self):
        folders = self.c_usr.run("ls -1").stdout.split()
        result = []
        for folder in folders:
            folder = folder.strip()
            elements = folder.split("-")
            if elements[0] == "django" \
               and elements[1].isnumeric():
                result.append(folder)
        return result
