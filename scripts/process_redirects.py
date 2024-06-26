import os
import shutil
import json
import uuid
import subprocess
import requests
import logging
from cryptography.fernet import Fernet
from os import environ
from enum import Enum

# TODO: Need to keep the old uuid's for a bit, to make sure there is always an asset to get!

# TODO: Add some sort of info json that people can use to add info about their projects and links to them
github_repo = "ModdersAgainstBlockers"
logger = logging.getLogger(__name__)


class RedirectType(Enum):
    LINK = 1
    IMG = 2


def auto_detect_type(url):
    if url.endswith(('.jpg', '.png', '.gif', '.jpeg', '.webp')):
        return RedirectType.IMG
    return RedirectType.LINK


def find_redirect_files(data_path):
    redirect_files = []
    for root, _, files in os.walk(data_path):
        for file in files:
            if file.endswith('redirects.json'):  # Allows appending to redirects file: mod-redirects.json
                redirect_files.append(os.path.join(root, file))
    return redirect_files


def process_redirect_file(repos, last_repos, file_path, template_content, output_dir):
    with open(file_path, 'r') as f:
        data = json.load(f)

    if 'repo_name' not in data:  # Must be a repo_name for it to be valid
        logger.warning(f"Missing Repo Name in: {file_path}")
        return 0

    repo_name = data['repo_name']
    if not repo_name:
        logger.warning(f"Invalid repo name in: {file_path} - {repo_name}")
        return 0
    repo_name = repo_name.lower()

    if 'redirects' not in data:  # Must be redirects for it to be valid
        logger.warning(f"Missing redirects in: {file_path}")
        return 0

    redirects = data['redirects']
    if len(redirects) == 0:
        logger.warning(f"No redirects in: {file_path}")
        return

    last_ids = []
    if repo_name in last_repos:
        last_ids = last_repos[repo_name]

    ids = []
    count = 0
    for redirect in data['redirects']:
        if 'url' not in redirect:  # If there's no URL, this is useless
            logger.warning(f"Redirect is missing URL in: {file_path}")
            continue

        url = redirect['url']

        if 'type' in redirect:  # Was type set manually, use this instead of detecting it.
            type_name = redirect['type']
            if type_name in RedirectType:
                url_type = RedirectType[type_name]
            else:
                logger.warning(f"Type: `{type_name}` is not a valid type in: {file_path} - {url}")
                continue
        else:
            url_type = auto_detect_type(url)

        if not url_type:
            continue

        if create_redirect(last_ids, ids, url_type, url, template_content, output_dir):
            count += 1
    if count > 0:
        repos[repo_name] = ids
    return count


def create_redirect(last_ids, ids, url_type, url, template_content, output_dir):
    unique_id = str(uuid.uuid4())  # Generate the unique uuid for the redirect

    if url_type == RedirectType.IMG:
        file_name = os.path.basename(url)
        extension = os.path.splitext(file_name)[1]
        # Download image from url, and save a copy within GitHub pages
        r = requests.get(url)
        with open(os.path.join(output_dir, unique_id + extension), 'wb') as outfile:
            outfile.write(r.content)

        to_url = f"{unique_id}{extension}"
    elif url_type == RedirectType.LINK:
        output_path = os.path.join(output_dir, unique_id)
        os.makedirs(output_path, exist_ok=True)

        to_url = f"{unique_id}/index.html"

        new_content = template_content.replace('||redirect_url||', url)

        with open(os.path.join(output_path, 'index.html'), 'w') as f:
            f.write(new_content)
    else:
        return False

    last_to = ''
    for id1 in last_ids:
        if id1['from'] == url:
            last_to = id1['to']
            break
    if last_to:
        ids.append({"from": url, "last_to": last_to, "to": to_url})
    else:
        ids.append({"from": url, "to": to_url})
    return True


def main():
    encryption_key = environ.get('ENCRYPTION_KEY')
    repo_path = '.'
    template_path = os.path.join(repo_path, 'templates', 'redirect.html')
    gh_pages_base_path = os.path.join(repo_path, 'gh-pages-base')
    data_path = os.path.join(repo_path, 'data')
    output_path = os.path.join(repo_path, 'docs')

    # Clean and prepare the gh-pages directory
    if os.path.exists(output_path):
        shutil.rmtree(output_path)
    shutil.copytree(gh_pages_base_path, output_path)

    with open(template_path, 'r') as f:
        template_content = f.read()

    repos = {}
    count = 0
    redirect_files = find_redirect_files(data_path)

    last_repos = {}
    encrypted_workflow_url = f"https://{github_repo}.github.io/encrypted_workflow_ids.json"
    rr = requests.get(encrypted_workflow_url)
    if rr.ok:
        domain = f"https://{github_repo}.github.io/"
        encrypted_repos = json.loads(rr.text)
        f = Fernet(encryption_key)
        for repo_name, ids in encrypted_repos.items():
            new_ids = []
            for id1 in ids:
                to = f.decrypt(id1['to']).decode()
                new_ids.append({
                    "from": f.decrypt(id1['from']).decode(),
                    "to": to
                })
                # Download last files to keep for another turn
                r = requests.get(domain + to)
                file = os.path.join(output_path, to)
                os.makedirs(os.path.dirname(file), exist_ok=True)
                with open(file, 'wb') as outfile:
                    outfile.write(r.content)
            last_repos[f.decrypt(repo_name).decode()] = new_ids
    else:
        logger.warning("`encrypted_workflow_ids.json` was not found! Is this a new repository? - " +
                       encrypted_workflow_url)

    for redirect_file in redirect_files:
        count += process_redirect_file(repos, last_repos, redirect_file, template_content, output_path)

    if count == 0:
        logger.warning(f"No redirects where created!")
        return

    # Set the secret workflow id's
    with open("workflow_ids.json", "w") as outfile:
        json.dump(repos, outfile)

    encrypted_repos = {}
    f = Fernet(encryption_key)
    for repo_name, ids in repos.items():
        new_ids = []
        for id1 in ids:
            new_ids.append({
                "from": f.encrypt(id1['from'].encode(encoding='utf-8')).decode(),
                "to": f.encrypt(id1['to'].encode(encoding='utf-8')).decode()
            })
        encrypted_repos[f.encrypt(repo_name.encode(encoding='utf-8')).decode()] = new_ids

    # Set the encrypted workflow id's
    with open(os.path.join(output_path, "encrypted_workflow_ids.json"), "w") as outfile:
        json.dump(encrypted_repos, outfile)

    # Change to gh-pages branch
    subprocess.run(['git', 'checkout', '-B', 'gh-pages'], check=True)

    logger.info(f"Done creating redirects - amount: {count}")


if __name__ == "__main__":
    logging.basicConfig()
    logging.root.setLevel(logging.NOTSET)
    logging.basicConfig(level=logging.NOTSET)
    logger.setLevel(logging.INFO)
    main()