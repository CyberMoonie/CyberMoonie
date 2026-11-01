#!/usr/bin/env python3
"""Refresh the live values in profile.svg: today's date, uptime and the GitHub stats.

The date and uptime are always updated. The stats need ACCESS_TOKEN, a token that can read
the private repositories too; without it they keep their last values.
"""
import html
import json
import os
import re
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SVG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile.svg")
BORN = date(2004, 8, 22)
TZ = ZoneInfo("Europe/Chisinau")
EMAILS = ["cristianlupasco2004@gmail.com", "96778614+CyberMoonie@users.noreply.github.com"]

REPOS = """query($after: String) { viewer {
  id login followers { totalCount }
  repositories(first: 100, after: $after, ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) {
    totalCount pageInfo { hasNextPage endCursor }
    nodes { name stargazerCount owner { login } } } } }"""

HISTORY = """query($owner: String!, $name: String!, $author: CommitAuthor!, $after: String) {
  repository(owner: $owner, name: $name) { defaultBranchRef { target { ... on Commit {
    history(first: 100, after: $after, author: $author) {
      pageInfo { hasNextPage endCursor } nodes { oid additions deletions } } } } } } }"""


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def uptime(born, today):
    y, m, d = today.year - born.year, today.month - born.month, today.day - born.day
    if d < 0:
        m -= 1
        d += (today.replace(day=1) - timedelta(days=1)).day     # days in the previous month
    if m < 0:
        y, m = y - 1, m + 12
    return f"{plural(y, 'year')}, {plural(m, 'month')}, {plural(d, 'day')}"


def graphql(token, query, **variables):
    req = urllib.request.Request("https://api.github.com/graphql",
                                 data=json.dumps({"query": query, "variables": variables}).encode(),
                                 headers={"Authorization": f"bearer {token}"})
    with urllib.request.urlopen(req) as r:
        out = json.load(r)
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]


def stats(token):
    repos, after = [], None
    while True:
        v = graphql(token, REPOS, after=after)["viewer"]
        page = v["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    owned = [r for r in repos if r["owner"]["login"] == v["login"]]

    # my commits on each default branch, matched by account and by commit email, counted once
    commits = {}
    for r in repos:
        for author in ({"id": v["id"]}, {"emails": EMAILS}):
            after = None
            while True:
                ref = graphql(token, HISTORY, owner=r["owner"]["login"], name=r["name"],
                              author=author, after=after)["repository"]["defaultBranchRef"]
                if ref is None:                                   # empty repository
                    break
                h = ref["target"]["history"]
                commits.update((c["oid"], (c["additions"], c["deletions"])) for c in h["nodes"])
                if not h["pageInfo"]["hasNextPage"]:
                    break
                after = h["pageInfo"]["endCursor"]
    add = sum(a for a, _ in commits.values())
    rem = sum(d for _, d in commits.values())
    return {"repo_data": f"{len(owned):,}", "contrib_data": f"{len(repos):,}",
            "star_data": f"{sum(r['stargazerCount'] for r in owned):,}",
            "commit_data": f"{len(commits):,}", "follower_data": f"{v['followers']['totalCount']:,}",
            "loc_data": f"{add - rem:,}", "loc_add": f"{add:,}", "loc_del": f"{rem:,}"}


def put(svg, tid, value):
    svg, n = re.subn(rf'(<tspan[^>]*\bid="{tid}"[^>]*>)[^<]*(</tspan>)',
                     lambda m: m.group(1) + html.escape(value) + m.group(2), svg)
    if n != 1:
        raise SystemExit(f"{tid} not found in profile.svg")
    return svg


def main():
    today = datetime.now(TZ).date()
    values = {"date_data": today.strftime("%Y.%m.%d"), "age_data": uptime(BORN, today)}
    token = os.environ.get("ACCESS_TOKEN")
    if token:
        try:
            values.update(stats(token))
        except Exception as e:                                    # e.g. an expired token: keep the date ticking
            print(f"::warning::GitHub stats not updated: {e}")
    else:
        print("ACCESS_TOKEN is not set: the stats keep their last values")
    svg = open(SVG, encoding="utf-8").read()
    for tid, value in values.items():
        svg = put(svg, tid, value)
    open(SVG, "w", encoding="utf-8").write(svg)
    for tid, value in values.items():
        print(f"{tid}: {value}")


if __name__ == "__main__":
    main()
