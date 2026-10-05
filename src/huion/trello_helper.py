import urllib.parse
import sys
import webbrowser

def generate_auth_url(api_key: str) -> str:
    params = {
        "expiration": "never",
        "name": "HuionNote Automation",
        "scope": "read,write,account",
        "response_type": "token",
        "key": api_key.strip()
    }
    return f"https://trello.com/1/authorize?{urllib.parse.urlencode(params)}"

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = generate_auth_url(sys.argv[1])
        print(f"\n🔗 Open this exact URL in your browser:\n\n{url}\n")
