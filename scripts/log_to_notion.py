import os
import requests

notion_token = os.environ["NOTION_TOKEN"]
database_id = os.environ["NOTION_DATABASE_ID"]

payload = {
    "parent": {"database_id": database_id},
    "properties": {
        "Title": {
            "title": [
                {
                    "text": {
                        "content": os.environ.get("COMMIT_MESSAGE", "Git push")
                    }
                }
            ]
        },
        "Repository": {
            "rich_text": [
                {
                    "text": {
                        "content": os.environ.get("REPOSITORY", "")
                    }
                }
            ]
        },
        "Branch": {
            "rich_text": [
                {
                    "text": {
                        "content": os.environ.get("BRANCH_NAME", "")
                    }
                }
            ]
        },
        "Author": {
            "rich_text": [
                {
                    "text": {
                        "content": os.environ.get("AUTHOR_NAME", "")
                    }
                }
            ]
        },
        "Commit SHA": {
            "rich_text": [
                {
                    "text": {
                        "content": os.environ.get("COMMIT_SHA", "")
                    }
                }
            ]
        },
        "Commit URL": {
            "url": os.environ.get("COMMIT_URL", "")
        },
    },
}

response = requests.post(
    "https://api.notion.com/v1/pages",
    headers={
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    },
    json=payload,
    timeout=10,
)

response.raise_for_status()
print("Logged to Notion")
