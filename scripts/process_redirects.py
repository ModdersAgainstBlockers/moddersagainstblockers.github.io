import os
import shutil
import json
import uuid
import subprocess
import requests
import logging
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


def process_redirect_file(repos, file_path, template_content, output_dir):
    with open(file_path, 'r') as f:
        data = json.load(f)

    if 'repo_name' not in data:  # Must be a repo_name for it to be valid
        logger.warning(f"Missing Repo Name in: {file_path}")
        return 0

    repo_name = data['repo_name']
    if not repo_name:
        logger.warning(f"Invalid repo name in: {file_path} - {repo_name}")
        return 0

    if 'redirects' not in data:  # Must be redirects for it to be valid
        logger.warning(f"Missing redirects in: {file_path}")
        return 0

    redirects = data['redirects']
    if len(redirects) == 0:
        logger.warning(f"No redirects in: {file_path}")
        return

    ids = []
    count = 0
    for redirect in data['redirects']:
        if 'url' not in redirect:  # If there's no URL, this is useless
            logger.warning(f"Redirect is missing URL in: {file_path}")
            continue

        url = redirect['url']

        if 'type' not in redirect:  # Was type set manually, use this instead of detecting it.
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

        if create_redirect(ids, url_type, url, template_content, output_dir):
            count += 1
    if count > 0:
        repos[repo_name] = ids
    return count


def create_redirect(ids, url_type, url, template_content, output_dir):
    unique_id = str(uuid.uuid4())  # Generate the unique uuid for the redirect

    if url_type == RedirectType.IMG:
        file_name = os.path.basename(url)
        extension = os.path.splitext(file_name)[1]
        # Download image from url, and save a copy within GitHub pages
        r = requests.get(url)
        with open(os.path.join(output_dir, unique_id + "." + extension), 'wb') as outfile:
            outfile.write(r.content)

        redirect_url = f"https://{github_repo}.github.io/{unique_id}.{extension}"
    elif url_type == RedirectType.LINK:
        output_path = os.path.join(output_dir, unique_id)
        os.makedirs(output_path, exist_ok=True)

        redirect_url = f"https://{github_repo}.github.io/{unique_id}/index.html"

        new_content = template_content.replace('||redirect_url||', url)

        with open(os.path.join(output_path, 'index.html'), 'w') as f:
            f.write(new_content)
    else:
        return False

    ids.append({"from": url, "to": redirect_url})
    logger.info(f"Processed `{url_type}` redirect at `{redirect_url}` to `{url}`")
    return True


def main():
    repo_path = '.'
    template_path = os.path.join(repo_path, 'templates', 'redirect.html')
    gh_pages_base_path = os.path.join(repo_path, 'gh-pages-base')
    data_path = os.path.join(repo_path, 'data')
    output_path = os.path.join(repo_path, 'gh-pages')

    # Clean and prepare the gh-pages directory
    if os.path.exists(output_path):
        shutil.rmtree(output_path)
    shutil.copytree(gh_pages_base_path, output_path)

    with open(template_path, 'r') as f:
        template_content = f.read()

    repos = {}
    count = 0
    redirect_files = find_redirect_files(data_path)
    for redirect_file in redirect_files:
        count += process_redirect_file(repos, redirect_file, template_content, output_path)

    if count == 0:
        logger.warning(f"No redirects where created!")
        return

    # Commit and push changes to gh-pages branch
    subprocess.run(['git', 'checkout', '-B', 'gh-pages'], check=True)
    #subprocess.run(['git', 'add', '-A'], check=True)
    #subprocess.run(['git', 'commit', '-m', 'Re-generate redirect files'], check=True)
    #subprocess.run(['git', 'push', 'origin', 'gh-pages', '--force'], check=True)
    #logger.info(f"Changes have been pushed!")

    with open("workflow_ids.json", "w") as outfile:
        json.dump(repos, outfile)
    logger.info(repos)  # Temp

    logger.info(f"Done creating redirects - amount: {count}")


if __name__ == "__main__":
    main()
