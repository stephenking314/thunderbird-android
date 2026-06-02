#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import requests
import re

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

def get_recent_matching_tags(pattern):
    output = git(
        "for-each-ref",
        "--sort=-creatordate",
        "--format=%(refname:short)",
        "refs/tags",
    )
    filtered = [line for line in output.splitlines() if re.search(pattern, line)]
    return filtered[:2]


def github_get(url):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "contributors-between-tags",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response


def github_compare(repo, older, newer):
    commits = []

    url = f"https://api.github.com/repos/{repo}/compare/{older}...{newer}"

    while True:
        response = github_get(url)
        data = response.json()

        page_commits = data.get("commits", [])
        commits.extend(page_commits)

        if "next" in response.links:
            url = response.links["next"]["url"]
        else:
            break

    return commits


def get_contributors(commits):
    contributors = {}
    for commit in commits:
        author = commit.get("author")

        if not author or not author.get("login"):
            continue

        author = commit.get("author").get("login")
        date = commit.get("commit").get("author").get("date")

        # Track the earliest commit of each author in this set
        if author not in contributors:
            contributors[author] = commit
        elif date < contributors[author].get("commit").get("author").get("date"):
            contributors[author] = commit

    return contributors


def is_first_commit(repo, author, date):
    url = f"https://api.github.com/repos/{repo}/commits?author={author}&until={date}&per_page=2"
    data = github_get(url).json()
    return len(data) == 1


def get_first_contributions(repo, contributors):
    first_contributions = {}
    for author, commit in contributors.items():
        date = commit.get("commit").get("author").get("date")
        if is_first_commit(repo, author, date):
            sha = commit.get("sha")
            url = f"https://api.github.com/repos/{repo}/commits/{sha}/pulls"
            commit_data = github_get(url).json()
            if commit_data and "number" in commit_data[0]:
                pr_num = commit_data[0].get("number")
                first_contributions[author] = f"#{pr_num}"

    return first_contributions


def main(args):
    print(args)

    tags = get_recent_matching_tags(args.regex)
    print(f"{tags=}")

    repo = args.repo

    if args.head:
        print(f"{args.head=}")
        if len(tags) < 1:
            print(f"Not enough tags matching pattern: {args.regex}", file=sys.stderr)
            sys.exit(1)

        older = tags[0]
        newer = args.head
        changelog_newer = args.changelog_head or args.head
    else:
        if len(tags) < 2:
            print(f"Not enough tags matching pattern: {args.regex}", file=sys.stderr)
            sys.exit(1)

        newer, older = tags[0], tags[1]
        changelog_newer = newer

    print("Getting commits...")
    commits = github_compare(repo, older, newer)
    print("Getting contribubors...")
    contributors = get_contributors(commits)
    print("Checking for first contributions...")
    first_contributions = get_first_contributions(repo, contributors)

    contributors = {f"@{author}" for author in contributors}
    excludes = {'@dependabot[bot]', '@thunderbird-botmobile[bot]', '@weblate'}
    contributors -= excludes
    print("producing output")
    with open(args.output_file, "w", encoding='utf-8') as f:
        print("\nContributors:", file=f)
        thanks_to = "Thanks to: " + ', '.join(sorted(contributors, key=str.casefold))
        print(thanks_to, file=f)

        if first_contributions:
            print("\nNew Contributors:", file=f)
            for author, pr in first_contributions.items():
                print(f"* @{author} made their first contribution in {pr}", file=f)

        changelog = f"https://github.com/thunderbird/thunderbird-android/compare/{older}...{changelog_newer}"
        print(f'\n**Full Changelog**: {changelog}', file=f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--head",
        help="Ref/SHA to compare against the latest matching tag"
    )
    parser.add_argument(
        "--changelog-head",
        help="Ref/tag to use in the Full Changelog link"
    )
    parser.add_argument(
        "--regex",
        "-r",
        default=r"^THUNDERBIRD_\d+_\d+$",
        help="Regex Pattern to use to search recent tags",
    )
    parser.add_argument(
        "--repo",
        default="thunderbird/thunderbird-android",
        help="github {owner}/{repository}"
    )
    parser.add_argument(
        "output_file",
        type=str,
        nargs="?",
        default="contributors",
        help="File to render contributors to",
    )
    args = parser.parse_args()
    main(args)
