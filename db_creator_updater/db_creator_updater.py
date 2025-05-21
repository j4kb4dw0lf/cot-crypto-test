import os
import subprocess
import sys

REPO_URL = "https://X"
LOCAL_PATH = "."
BUILD_COMMAND = "Y"
COMMIT_FILE = os.path.join(LOCAL_PATH, ".last_commit")

def get_remote_commit(repo_url):
    result = subprocess.run(
        ["git", "ls-remote", repo_url, "HEAD"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        print("Error fetching remote commit:", result.stderr)
        sys.exit(1)
    return result.stdout.split()[0]

def get_local_commit(path):
    if not os.path.isdir(os.path.join(path, ".git")):
        return None
    result = subprocess.run(
        ["git", "-C", path, "rev-parse", "HEAD"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()

def save_commit(commit_hash):
    with open(COMMIT_FILE, "w") as f:
        f.write(commit_hash)

def load_saved_commit():
    if not os.path.exists(COMMIT_FILE):
        return None
    with open(COMMIT_FILE, "r") as f:
        return f.read().strip()

def clone_and_build():
    subprocess.check_call(["git", "clone", REPO_URL, LOCAL_PATH])
    subprocess.check_call(BUILD_COMMAND, shell=True)

def update_and_build():
    subprocess.check_call(["git", "-C", LOCAL_PATH, "pull"])
    subprocess.check_call(BUILD_COMMAND, shell=True)

def update():
    remote_commit = get_remote_commit(REPO_URL)
    local_commit = get_local_commit(LOCAL_PATH)
    saved_commit = load_saved_commit()

    if local_commit is None:
        print("Local repo not found. Cloning and building...")
        clone_and_build()
        save_commit(remote_commit)
    elif remote_commit != saved_commit:
        print("Remote repo updated. Pulling and rebuilding...")
        update_and_build()
        save_commit(remote_commit)
    else:
        print("Repo is up to date. No action needed.")