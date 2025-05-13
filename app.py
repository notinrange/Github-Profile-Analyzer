import os
import json
import tempfile
import subprocess
import requests
from flask import Flask, render_template, request, redirect, url_for
from git import Repo
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sklearn.cluster import HDBSCAN
from markdown import markdown
from markupsafe import Markup

# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# directly giving gemini api key
GEMINI_API_KEY = "AIzaSyAv2nr1Pt1y55bPg9wBDSC45RLHPsBp85w"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.5-pro-preview-05-06:generateContent?key={GEMINI_API_KEY}"
)
# GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
# setuping github token for Authorization
GITHUB_TOKEN = "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"
HEADERS_GH = {"Authorization": f"token {GITHUB_TOKEN}"}

app = Flask(__name__)


@app.template_filter('markdown')
def markdown_to_html(text):
    html = markdown(text or '',
                    extensions=['fenced_code', 'tables', 'nl2br'])
    return Markup(html)

# simply we are getting status of repos 
def gh_get(url):
    resp = requests.get(url, headers=HEADERS_GH)
    resp.raise_for_status()
    return resp.json()


# top post a request we need github oauth2 api thats why we are sending headers for authentication
def gh_post(url, data):
    resp = requests.post(url, headers=HEADERS_GH, json=data)
    resp.raise_for_status()
    return resp.json()


# getting repos of user
def get_user_repositories(username):
    return gh_get(f"https://api.github.com/users/{username}/repos")


# getting languages of repo
def get_repo_languages(full_name):
    return gh_get(f"https://api.github.com/repos/{full_name}/languages")



# reanking repos by the complexity which we received by api of github
def rank_by_complexity(repos):
    scored = []
    for r in repos:
        langs = get_repo_languages(r["full_name"])
        complexity = sum(langs.values())
        r["complexity"] = complexity
        scored.append(r)
    return sorted(scored, key=lambda x: x["complexity"], reverse=True)

# cloning repos to analyze
def clone_repo(full_name):
    tmp = tempfile.mkdtemp()
    url = f"https://github.com/{full_name}.git"
    return Repo.clone_from(url, tmp).working_dir


# in this function we are giving prompt to gemini
def call_gemini(prompt_text):
    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
    resp = requests.post(GEMINI_URL, json=payload)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


# to cluster repos of profile we need embedding model which is not available for gemini free plan
def cluster_repositories(repos):
    texts = []
    for r in repos:
        readme = ""
        try:
            # Try fetch README via GitHub API
            rd = gh_get(f"https://api.github.com/repos/{r['full_name']}/readme")
            content = rd.get("content", "")
            readme = content.encode("utf-8").decode("base64")
        except Exception:
            pass
        texts.append(f"{r['description'] or ''}\n{readme}")

    embedder = GoogleGenerativeAIEmbeddings(model="models/text-embedding-005")
    vectors = embedder.embed_documents(texts)
    clusterer = HDBSCAN(min_cluster_size=2)
    labels = clusterer.fit_predict(vectors)
    for r, lbl in zip(repos, labels):
        r["cluster"] = int(lbl)
    return repos


# Here we are detecting smell of repository but we need sonar scanner for that which is not possible while hosting
# def scan_code_smells(repo_path):
#     # Example: run SonarQube Scanner if configured locally
#     result = subprocess.run(
#         ["sonar-scanner", "-Dsonar.projectBaseDir=" + repo_path],
#         capture_output=True,
#         text=True,
#     )
#     # Extract the summary from logs (placeholder)
#     return result.stdout.splitlines()[-10:]


# currently 
def summarize_smells(issues):
    text = "Summarize these code issues with fixes:\n" + "\n".join(issues)
    return call_gemini(text)


# configuring developer skills by scanning their repository
def profile_skills(repos):
    summary = "\n".join(
        f"{r['name']}: {r['language']} ({r['stargazers_count']} stars)"
        for r in repos
    )
    prompt = (
        "Based on this portfolio, describe the developer’s core skills "
        "and growth areas:\n" + summary
    )
    return call_gemini(prompt)


# in this function we are getting all meta data of repository to check their complexity 
def draft_readme(repo):
    meta = (
        f"Name: {repo['name']}\n"
        f"Description: {repo.get('description','')}\n"
        f"Languages: {repo.get('language','')}\n"
        f"Stars: {repo.get('stargazers_count',0)}"
    )
    prompt = "Generate a GitHub README.md with sections for install, usage, and contributing based on:\n" + meta
    return call_gemini(prompt)


#In this function we are predicting tags of repositories
def predict_tags(repo, candidates=None):
    candidates = candidates or [
        "machine-learning", "backend", "frontend", "devops", "cli", "data-science"
    ]
    tags_str = ", ".join(candidates)
    prompt = (
        f"Given description: “{repo.get('description','')}”, "
        f"select top 3 tags from: {tags_str}"
    )
    out = call_gemini(prompt)
    return [t.strip() for t in out.split(",")]


def update_github_topics(full_name, tags):
    url = f"https://api.github.com/repos/{full_name}/topics"
    data = {"names": tags}
    return gh_post(url, data)


# ── Flask Routes ───────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form["username"]
        repos = get_user_repositories(username)
        ranked = rank_by_complexity(repos)
        top = ranked[:2]

        # Clone & analyze top N
        enhancements = []
        for repo in top:
            path = clone_repo(repo["full_name"])
            # smells = scan_code_smells(path)
            enhancements.append({
                "repo": repo,
                # "smell_summary": summarize_smells(smells),
                "readme": draft_readme(repo),
                "tags": predict_tags(repo),
            })
            # update_github_topics(repo["full_name"], enhancements[-1]["tags"])

        # clusters = cluster_repositories(top)
        profile = profile_skills(repos)

        return render_template(
            "result.html",
            enhancements=enhancements,
            # clusters=clusters,
            profile=profile,
        )
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)



# summarize_smells
# update_github_topics
# cluster_repositories
