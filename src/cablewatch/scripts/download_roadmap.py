#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup


def main():
    try:
        import _bootstrap_package # noqa: F401
    except ImportError:
        pass
    from cablewatch import config
    conf = config.Config()
    response = requests.get(f'{conf.ROADMAP_HACKMD_URL}')
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    div = soup.find("div", id="publish-page")
    if not div:
        raise AssertionError("Cannot find publish page")
    with open("ROADMAP.md", 'w') as f:
        f.write(div.get_text(strip=True))


if __name__ == '__main__':
    main()
