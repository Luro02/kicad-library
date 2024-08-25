# Based on https://github.com/espressif/kicad-libraries/blob/main/package.py
# Some samples are in here:https://gitlab.com/kicad/addons/metadata
import json
import zipfile
import re
import hashlib
import sys

from datetime import datetime, timezone
from pathlib import Path

DIRECTORIES_TO_ZIP = [
    Path("3dmodels"),
    Path("footprints"),
    Path("symbols"),
    Path("resources"),
]

KICAD_VERSION = "8.0.0"
ZIP_FILE_NAME = "package.zip"
DOWNLOAD_URL = "https://github.com/Luro02/kicad-library/releases/download/{VERSION}/{ZIP_FILE_NAME}"
MAIN_URL = "https://raw.githubusercontent.com/Luro02/kicad-library/main/{FILE_NAME}"

def create_json_string(zip_internal_metadata_json: dict):
    return json.dumps(zip_internal_metadata_json, indent=4)

def read_template_json_file():
    with open('metadata.template.json', mode='r') as metadata_file:
        metadat_template = json.load(metadata_file)
        metadata_file.close()

        return metadat_template

def create_zip_internal_metadata_json(version: str):
    template = read_template_json_file()
    version_item = {
        "version": version,
        "status": "stable",
        "kicad_version": KICAD_VERSION
    }

    template["versions"] = [version_item]

    return template

def create_full_metadata_file(version: str, existing_versions: list, zip_size: int, zip_internal_size: int, zip_file_sha256: str):
    template = read_template_json_file()

    download_url = DOWNLOAD_URL.replace("{VERSION}", version).replace("{ZIP_FILE_NAME}", ZIP_FILE_NAME)

    version_item = {
        "version": version,
        "status": "stable",
        "kicad_version": KICAD_VERSION,
        "download_sha256": zip_file_sha256,
        "download_size": zip_size,
        "download_url": download_url,
        "install_size": zip_internal_size
    }
    existing_versions.insert(0, version_item)

    template['versions'] = existing_versions

    with open('metadata.json', mode='w') as metadata_file:
        metadata_file.write(create_json_string(template))

    return template

def calculate_zip_content_size(zip_handle: zipfile.ZipFile) -> int:
    zip_content_size = 0
    for entry in zip_handle.infolist():
        if not entry.is_dir():
            zip_content_size += entry.file_size

    return zip_content_size

# Return internal size
def generate_release_zip_file(zip_file_path: Path, version: str) -> int:
    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_handle:
        # add all directories to the zip file:
        for directory_to_zip in DIRECTORIES_TO_ZIP:
            # go through all files in the directory to zip
            for path in directory_to_zip.rglob("*"):
                # and add them to the zip file
                zip_handle.write(path, path)

        zip_handle.writestr('metadata.json', create_json_string(create_zip_internal_metadata_json(version)))

        return calculate_zip_content_size(zip_handle)

def hash_data_sha256(data) -> str:
    return hashlib.sha256(data).hexdigest()

def hash_file_sha256(filepath: Path) -> str:
    with open(filepath, "rb") as fd:
        return hashlib.file_digest(fd, 'sha256', _bufsize=65536).hexdigest()

def read_all_existing_versions():
    if Path('metadata.json').is_file():
        with open('metadata.json') as f:
            metadata_file = json.load(f)
            f.close()
            if 'versions' in metadata_file:
                return metadata_file['versions']
    return []

def get_version_from_user():
    version = input("Enter the new addon version (required format: major[.minor[.patch]]): ")
    return version.strip()

def generate_repository_file(metadata, version):
    with open("repository.template.json", "rb") as fd:
        repo_template = json.load(fd)

    # create "packages" and "resources" sections?
    with open("packages.json", "w") as fd:
        fd.write(create_json_string({ "packages": [dict(metadata)] }))

    utc_time = datetime.now(timezone.utc)
    update_time_utc = utc_time.strftime('%Y-%m-%d %H:%M:%S')
    update_timestamp = int(utc_time.timestamp())

    repo_template["packages"] = {
        "sha256": hash_file_sha256(Path("packages.json")),
        "update_time_utc": update_time_utc,
        "update_timestamp": update_timestamp,
        "url": MAIN_URL.replace("{FILE_NAME}", "packages.json"),
    }

    # create the resources.zip file which contains the icon:
    
    # the resources zip file looks like this:
    # /
    # - com.github.user.plugin-name
    #   - icon.png

    # -> metadata["identifier"] for folder name
    # -> resources/icon.png for the icon

    zip_resources_path = Path('build') / "resources.zip"
    resources_path = Path('resources')
    with zipfile.ZipFile(zip_resources_path, 'w', zipfile.ZIP_DEFLATED) as zip_handle:
        zip_handle.write(resources_path / "icon.png", f'{metadata["identifier"]}/icon.png')

    repo_template["resources"] = {
        "sha256": hash_file_sha256(zip_resources_path),
        "update_time_utc": update_time_utc,
        "update_timestamp": update_timestamp,
        "url": DOWNLOAD_URL.replace("{VERSION}", version).replace("{ZIP_FILE_NAME}", "resources.zip"),
    }

    with open("repository.json", "w") as fd:
        fd.write(create_json_string(repo_template))

if __name__ == "__main__":
    print('This script helps to generate a new kicad addon release. \n')
    print('It generates the release zip file and the metadata.json \n\n')

    if len(sys.argv) < 2:
        version = get_version_from_user()
    else:
        version = sys.argv[1]

    if not re.match('^\\d{1,4}(\\.\\d{1,4}(\\.\\d{1,6})?)?$', version):
        raise ValueError(
            "Version string is invalid. Required format: major[.minor[.patch]] (major, minor, patch are numbers)")

    existing_versions = read_all_existing_versions()
    if version in [version_data["version"] for version_data in existing_versions]:
        raise ValueError("The specified version " + version + " already exists")

    print("Start packaging documents to zip\n")
    build_dir = Path("build/")
    build_dir.mkdir(exist_ok=True)

    zip_file_path = build_dir / ZIP_FILE_NAME
    # remove old files:
    zip_file_path.unlink(missing_ok=True)

    zip_internal_size = generate_release_zip_file(zip_file_path, version)
    zip_sha256 = hash_file_sha256(zip_file_path)
    zip_size = zip_file_path.stat().st_size

    print(f'Generated addon zip at path: {zip_file_path}\n')
    print('Starting to generate metadata.json\n')
    metadata = create_full_metadata_file(version, existing_versions, zip_size, zip_internal_size, zip_sha256)

    generate_repository_file(metadata, version)

    print('All necessary files have been generated.')
