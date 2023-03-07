from bs4 import BeautifulSoup 
from python_graphql_client import GraphqlClient
import datetime
import feedparser
import httpx
import json
import pathlib
import re
import requests
import os

headers = {
        'Content-Type': 'text/html;charset=UTF-8',
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36"
        }

root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")

TOKEN = os.environ.get("GH_TOKEN", "")

def fetch_data(url):
    try:
        respones = requests.get(url,headers = headers)
        respones.encoding = 'utf-8'
        if respones.status_code == 200:
            return respones.text
        return None
    except RequestException:
        print('请求索引页错误')
        return None
        
def replace_chunk(content, marker, chunk, inline=False):
    r = re.compile(
            r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
            re.DOTALL,
            )
    if not inline:
        chunk = "\n{}\n".format(chunk)
    chunk = "<!-- {} starts -->{}<!-- {} ends -->".format(marker, chunk, marker)
    return r.sub(chunk, content)

def formatGMTime(timestamp):
    GMT_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
    dateStr = datetime.datetime.strptime(timestamp, GMT_FORMAT) + datetime.timedelta(hours=8)
    return dateStr.date()

def make_query(after_cursor=None):
    return """
query {
  viewer {
    repositories(first: 100, privacy: PUBLIC, after:AFTER) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        name
        description
        url
        releases(last:1) {
          totalCount
          nodes {
            name
            publishedAt
            url
          }
        }
      }
    }
  }
}
""".replace(
        "AFTER", '"{}"'.format(after_cursor) if after_cursor else "null"
        )


def fetch_releases(oauth_token):
    repos = []
    releases = []
    repo_names = set()
    has_next_page = True
    after_cursor = None

    while has_next_page:
        data = client.execute(
                query=make_query(after_cursor),
                headers={"Authorization": "Bearer {}".format(oauth_token)},
                )
        print()
        print(json.dumps(data, indent=4))
        print()
        for repo in data["data"]["viewer"]["repositories"]["nodes"]:
            if repo["releases"]["totalCount"] and repo["name"] not in repo_names:
                repos.append(repo)
                repo_names.add(repo["name"])
                releases.append(
                        {
                            "repo": repo["name"],
                            "repo_url": repo["url"],
                            "description": repo["description"],
                            "release": repo["releases"]["nodes"][0]["name"]
                            .replace(repo["name"], "")
                            .strip(),
                            "published_at": repo["releases"]["nodes"][0][
                                "publishedAt"
                                ].split("T")[0],
                            "url": repo["releases"]["nodes"][0]["url"],
                            }
                        )
        has_next_page = data["data"]["viewer"]["repositories"]["pageInfo"][
                "hasNextPage"
                ]
        after_cursor = data["data"]["viewer"]["repositories"]["pageInfo"]["endCursor"]
    return releases


def fetch_code_time():
    return httpx.get(
            "https://gist.githubusercontent.com/marsczen/0c39a3e7b4a372c6cff4a8714271308c/raw/"
            )

if __name__ == "__main__":
    readme = root / "README.md"
    project_releases = root / "releases.md"
    releases = fetch_releases(TOKEN)
    releases.sort(key=lambda r: r["published_at"], reverse=True)
    md = "\n".join(
            [
                "* <a href='{url}' target='_blank'>{repo} {release}</a> - {published_at}".format(**release)
                for release in releases[:5]
                ]
            )
    readme_contents = readme.open().read()
    rewritten = replace_chunk(readme_contents, "recent_releases", md)

    # Write out full project-releases.md file
    project_releases_md = "\n".join(
            [
                (
                    "* **[{repo}]({repo_url})**: [{release}]({url}) - {published_at}\n"
                    "<br>{description}"
                    ).format(**release)
                for release in releases
                ]
            )
    project_releases_content = project_releases.open().read()
    project_releases_content = replace_chunk(
            project_releases_content, "recent_releases", project_releases_md
            )
    project_releases_content = replace_chunk(
            project_releases_content, "release_count", str(len(releases)), inline=True
            )
    project_releases.open("w").write(project_releases_content)

    code_time_text = "\n```text\n"+fetch_code_time().text+"\n```\n"

    rewritten = replace_chunk(rewritten, "code_time", code_time_text)

    readme.open("w").write(rewritten)
