#!/usr/bin/python3
import sys
import caller_config
import subprocess


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
    if len(sys.argv) <= 1:
        print("Missing arguments")
        sys.exit(1)
    elif len(sys.argv) == 2:
        code_commit = sanitize_commit_info(sys.argv[1])
        config_commit = sanitize_commit_info(
            get_master_hash_of_repo(caller_config.config_repo)
        )
    elif len(sys.argv) == 3:
        code_commit = sanitize_commit_info(sys.argv[1])
        config_commit = sanitize_commit_info(sys.argv[2])
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
