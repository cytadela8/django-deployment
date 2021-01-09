#!/usr/bin/python3
import sys
import caller_config
import subprocess
import os

def sanitize_commit_info(commit: str):
    commit = commit.strip()
    if not commit.isalnum():
        return None
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
    if len(args) == 0:
        print("Missing arguments")
        sys.exit(1)
    elif len(args) == 1:
        code_commit = sanitize_commit_info(args[0])
        config_commit = sanitize_commit_info(
            get_master_hash_of_repo(caller_config.config_repo)
        )
    elif len(args) == 2:
        code_commit = sanitize_commit_info(args[0])
        config_commit = sanitize_commit_info(args[1])
    else:
        print("Too many arguments")
        sys.exit(1)

    if not code_commit:
        print("Invalid code commit")
        sys.exit(1)
    if not config_commit:
        print("Invalid config commit")
        sys.exit(1)
    subprocess.call(
        [caller_config.fab_path, "deploy", code_commit, config_commit],
        cwd=caller_config.deployment_script_root,
    )


if __name__ == "__main__":
    main()
