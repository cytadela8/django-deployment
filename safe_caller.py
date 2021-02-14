#!/usr/bin/python3
import sys
import caller_config
import subprocess
import os
from filelock import FileLock


class InvalidCommit(Exception):
    pass


def sanitize_commit_info(commit: str) -> str:
    commit = commit.strip()
    if not commit.isalnum():
        raise InvalidCommit()
    return commit


def get_master_hash_of_repo(url: str):
    return subprocess.check_output(
            ["git", "ls-remote", url, "refs/heads/master"]
        ).decode('ascii').split("\t")[0]


def main():
    args = sys.argv[1:]
    if 'SSH_ORIGINAL_COMMAND' in os.environ:
        print("Looking at original SSH command...", flush=True)
        args = os.environ['SSH_ORIGINAL_COMMAND'].strip().split(' ')
    try:
        if len(args) == 1:
            code_commit = sanitize_commit_info(args[0])
            config_commit = sanitize_commit_info(
                get_master_hash_of_repo(caller_config.config_repo)
            )
        elif len(args) == 2:
            code_commit = sanitize_commit_info(args[0])
            config_commit = sanitize_commit_info(args[1])
        else:
            print("Wrong number of arguments - " + str(len(args)))
            sys.exit(1)
        lock = FileLock("deploy.lock")
        with lock:
            ret = subprocess.call(
                [caller_config.fab_path, "deploy", code_commit, config_commit],
                cwd=caller_config.deployment_script_root,
            )
        if ret != 0:
            if ret < 0:
                print("Killed by signal", -ret)
                sys.exit(2)
            else:
                print("Command failed with return code", ret)
                sys.exit(ret)
        else:
            print("SUCCESS!!")
    except InvalidCommit:
        print("Invalid commit")
        sys.exit(1)


if __name__ == "__main__":
    main()
