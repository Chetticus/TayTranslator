"""Explicit one-time model download; the translation server never downloads models."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import requests

ROOT = Path(__file__).resolve().parent / "models" / "english"
MODELS = {pair: f"https://argos-net.com/v1/translate-{pair}-1_9.argosmodel" for pair in ("en_vi", "vi_en")}


def install(pair, url):
    target = ROOT / pair
    if (target / "installation.json").exists():
        print(f"Already installed: {pair}", flush=True)
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    archive = ROOT / f"{pair}.argosmodel"
    if not archive.exists():
        temporary = ROOT / f"{pair}.download"
        print(f"Downloading {pair} from {url}", flush=True)
        with requests.get(url, stream=True, timeout=(15, 90)) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                size = 0
                for block in response.iter_content(1024 * 1024):
                    size += len(block)
                    if size > 500 * 1024 * 1024:
                        raise ValueError("Model archive exceeds 500 MB limit")
                    handle.write(block)
        temporary.rename(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    files = {}
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if sum(m.file_size for m in members) > 1500 * 1024 * 1024:
            raise ValueError("Unpacked archive exceeds size limit")
        metadata_name = next(m.filename for m in members if m.filename.endswith('/metadata.json'))
        prefix = metadata_name.removesuffix('metadata.json')
        metadata = json.loads(package.read(metadata_name))
        if f"{metadata['from_code']}_{metadata['to_code']}" != pair:
            raise ValueError("Wrong language package")
        for member in members:
            if not member.filename.startswith(prefix) or member.is_dir():
                continue
            relative = member.filename[len(prefix):]
            if not (relative.startswith('model/') or relative in ('sentencepiece.model', 'metadata.json') or 'license' in relative.lower() or 'readme' in relative.lower()):
                continue
            destination = (target / relative).resolve()
            if not destination.is_relative_to(target.resolve()):
                raise ValueError("Unsafe archive path")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with package.open(member) as source, destination.open('wb') as output:
                shutil.copyfileobj(source, output)
            files[relative] = hashlib.sha256(destination.read_bytes()).hexdigest()
    if not (target / 'model/model.bin').exists() or not (target / 'sentencepiece.model').exists():
        raise ValueError("Incomplete model archive")
    (target / 'installation.json').write_text(json.dumps({"url":url,"archive_sha256":digest,"files":files,"metadata":metadata}, indent=2), encoding='utf-8')
    print(f"Installed {pair}; archive SHA256 {digest}", flush=True)


if __name__ == '__main__':
    for pair, url in MODELS.items():
        install(pair, url)
