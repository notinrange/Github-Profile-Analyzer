import requests
import json
import gpt
import langchain
from flask import Flask, render_template, request

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        user_name = request.form["username"]
        most_complex_repository = get_most_complex_repository(user_name)
        return render_template("result.html", repository=most_complex_repository)
    return render_template("index.html")


def get_github_user_profile(username):
    url = "https://api.github.com/users/" + username
    response = requests.get(url)
    data = json.loads(response.content)
    return data

def get_user_repositories(username):
    url = "https://api.github.com/users/" + username + "/repos"
    response = requests.get(url)
    data = json.loads(response.content)
    return data


def get_repository_complexity(repo_url):
    # Retrieve the repository information
    response = requests.get(f"https://api.github.com/repos/{repo_url}")
    if response.status_code != 200:
        raise Exception("Failed to retrieve repository information.")

    repository_data = json.loads(response.text)
    repository_full_name = repository_data["full_name"]

    # Retrieve the repository languages
    response = requests.get(f"https://api.github.com/repos/{repository_full_name}/languages")
    if response.status_code != 200:
        raise Exception("Failed to retrieve repository languages.")

    languages_data = json.loads(response.text)

    # Calculate the repository complexity
    complexity = sum(languages_data.values())

    return complexity


def get_most_complex_repository(username):
    user_profile = get_github_user_profile(username)
    user_repositories = get_user_repositories(username)
    most_complex_repository = None
    most_complex_complexity = 0
    for repository in user_repositories:
        complexity = get_repository_complexity(repository['full_name'])
        if complexity > most_complex_complexity:
            most_complex_repository = repository
            most_complex_complexity = complexity
    return most_complex_repository['full_name']

def main():
    user_name = input("Enter the GitHub user's name : ")
    most_complex_repository = get_most_complex_repository(user_name)
    print("The most technically complex repository is:", most_complex_repository)

if __name__ == "__main__":
    
    app.run(debug=True)

