# Google Drive file transfer

The purpose of this script is to transfer a Google Drive file or folder (recursively) from one user to another, or to a shared drive. Only docs/folders owned by the source user are affected, all others are ignored. When moving files or folders to a shared drive, the source user must be a member of the shared drive.

## Installation

This script requires Python 3. The `requirements.txt` file contains all the Python dependencies:

```
pip3 install -r requirements.txt
```

## Obtaining credentials

In order to run the script, you need to provide credentials for a service account stored in a JSON file. The service account you create **must** have delegated domain-wide authority. Follow [these instructions](https://developers.google.com/identity/protocols/OAuth2ServiceAccount#creatinganaccount).

## Usage

```
$ python3 transfer.py --help
usage: transfer.py [-h] --creds CREDS [--folder FOLDER] [--file FILE] [--files FILES] --source SOURCE [--target-owner TARGET_OWNER] [--target-drive TARGET_DRIVE]
                   [--target-drive-folder TARGET_DRIVE_FOLDER] [--verbose] [--debug]

The purpose of this script is to transfer a Google Drive file or folder (recursively) from one user to another, or to a shared drive. Only docs/folders owned by the source user are
affected, all others are ignored. When moving files or folders to a shared drive, the source user must be a member of the shared drive.

options:
  -h, --help            show this help message and exit
  --creds CREDS         Service account credentials file (e.g. credentials.json)
  --folder FOLDER       ID of folder to transfer or move
  --file FILE           ID of file to transfer or move
  --files FILES         Filename of text file that includes IDs of file to transfer or move
  --source SOURCE       Email address of person who currently owns the file(s) (e.g. alice@example.com)
  --target-owner TARGET_OWNER
                        Email address of person the file(s) ownership should be transferred to (e.g. bob@example.com)
  --target-drive TARGET_DRIVE
                        ID of the shared drive to move file(s) to (NOTE: source user must be member of the drive)
  --target-drive-folder TARGET_DRIVE_FOLDER
                        ID of the folder within the shared drive to move file(s) to
  --verbose             Print all Google API requests to the console
  --debug               Print all HTTP request and response headers and bodies to the console
```

Example usage:

```
$ python3 transfer.py --creds credentials.json --folder 1kuKqN3KLRWlUz3ra1pN1wscgd5tZo_5g --source alice@example.com --target-owner bob@example.com

$ python3 transfer.py --creds credentials.json --file 1GPPBP40faGOPwuKWiagpW3pzBhx-OPwWOlF-RCnuybM --source eve@example.com --target-drive 0AMRjD67Q48VeUk9PVA --target-drive-folder 1kuKqN3KLRWlUz3ra1pN1wscgd5tZo_5g --verbose
```
