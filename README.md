# Django Deployment Automation
[fabric-based](https://www.fabfile.org/) script for Django
deployment automation with limited downtime and safety in mind. 

The core of this script is the "deploy" command designed to perform a 
non-destructive update of Django with multiple checks and fallback
procedures designed to revert changes in case of failure. This script also
provides a few other commands for cleaning, checks and manual reverting to 
previous code versions.

## Installation

### Dependencies

Make sure you have all Python dependencies installed (see requirements.txt) 
for python3. To install in a virtual environment execute:

```shell
$ python3 -m venv venv
$ source venv/bin/activate
(venv) $ pip install -r requirements.txt
```

### Configuration

Create `fabric.yml` file in script root directory/root directory of this repo. 
A minimal configuration file can be found in `fabric.yml.example`.

### Safe shell access

TODO

## Usage

All commands can be listed by executing `fab --list`.

You can get more info about each command with `fab --help COMMAND_NAME`.

## Configuration options

IMPORTANT: This scripts makes following assumptions about the production
environment:

- user "app" manages the Django App code and config
- user "admin" has sudo access
- configuration variables in fabric.yml are set correctly
- scripts:
    - all return a non zero exit code on failure
    - ~app/scripts/backup_database.sh - backups the Django App database
        - assumed that it outputs backup path
    - ~app/scripts/start_maintenance.sh - performs pre app update tasks
    - ~app/scripts/stop_maintenance.sh - performs post app update tasks (run
      also when update failed, but start_maintenance was run before)
- Systemd django.service manages the Django App supervisord
- symlinks:
    - ~app/django-current, ~app/django-previous, ~app/django-working,
      ~app/django-previous-working - are valid symlinks to the Django App
      Versions directories (see below for definition of the Django App version
      directory)
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