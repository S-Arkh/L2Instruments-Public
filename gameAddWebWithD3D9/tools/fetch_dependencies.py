"""Install build dependencies into the ignored SDK directory."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--webview-version', default='1.0.4314.35')
    parser.add_argument('--webview-package', type=Path, help='Use an already downloaded NuGet archive')
    args = parser.parse_args()
    import nlohmann_json
    include = Path(nlohmann_json.get_include())
    shutil.copytree(include, ROOT/'sdk/json', dirs_exist_ok=True)
    vendor = ROOT/'profiles/high-five/vendor'
    shutil.copytree(include, vendor, dirs_exist_ok=True)
    url = ('https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/'
           f'{args.webview_version}/microsoft.web.webview2.{args.webview_version}.nupkg')
    data = args.webview_package.read_bytes() if args.webview_package else urllib.request.urlopen(url, timeout=120).read()
    destination = ROOT/'sdk/webview2'
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if not (destination/name).resolve().is_relative_to(destination.resolve()):
                raise ValueError('Invalid archive member')
        archive.extractall(destination)
    (destination/'download.json').write_text(json.dumps(dict(url=url, sha256=hashlib.sha256(data).hexdigest()), indent=2))
    print('Installed JSON headers and WebView2 SDK:', destination)


if __name__ == '__main__':
    main()
