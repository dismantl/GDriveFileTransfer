import argparse
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']
BATCH_SIZE = 10  # Max: 100


# Generate an API service using the passed JSON credentials file
# See: https://developers.google.com/identity/protocols/OAuth2ServiceAccount#authorizingrequests
def authorized_api(api_name, api_version, credentials_file, source_email):
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file, scopes=SCOPES)
    # Use service account to impersonate the source user
    credentials = credentials.with_subject(source_email)
    return build(api_name, api_version, credentials=credentials)


# Build a list of top level folder and all folders within it
def get_all_folders(drive, top_folder_id):
    all_folders = [top_folder_id]
    def recurse_folder(folder_id, folder_name='[Unknown]'):
        folders = []
        print(f'Recursing folder {folder_name} ({folder_id})')
        request = drive.files().list(
            q=f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder'",
            pageSize=1000,
            fields="files(id, name, owners)"
        )
        while request is not None:
            results = request.execute()
            folders += results.get('files', [])
            request = drive.files().list_next(request, results)

        for folder in folders:
            all_folders.append(folder['id'])
            recurse_folder(folder['id'], folder['name'])

    recurse_folder(top_folder_id, '[top level folder]')
    return all_folders


# Build a list of files that are in any of the folders in folders_list
def get_all_files(drive, folders_list):
    # Build query to send to Drive API, using the generated folder list
    q = ''
    for folder_id in folders_list[:-1]:
        q += f"'{folder_id}' in parents or "
    q += f"'{folders_list[-1]}' in parents"

    # Get list of docs/folders matching the query
    files = []
    print('Querying for list of files')
    request = drive.files().list(
        q=q,
        pageSize=1000,
        fields="files(id, name, owners)"
    )
    while request is not None:
        results = request.execute()
        files += results.get('files',[])
        request = drive.files().list_next(request, results)

    print(f'Found {len(files)} files')
    return files


# basic callback function needed for API batch requests
def batch_callback(request_id, response, exception):
    if exception:
        # Handle error
        raise exception
    # else:
    #     print(response)


# Takes a list of Google files/folders and assigns ownership to the target user
# for all files/folders owned by the source user
def reassign_ownership(drive, files, source_email, target_email):
    # Create a permission object assigning ownership to our target account
    user_permission = {
        'type': 'user',
        'role': 'owner',
        'emailAddress': target_email
    }

    # Filter files to only ones owned by the source user
    files = list(filter(lambda file: source_email in [owner['emailAddress'] for owner in file['owners']]))

    # Call Drive API in batches to re-assign ownership
    chunks = [files[i:i + BATCH_SIZE] for i in range(0, len(files), BATCH_SIZE)]
    for chunk in chunks:
        print(f'Transferring ownership of {len(chunk)} files')
        batch = drive.new_batch_http_request(callback=batch_callback)
        for file in chunk:
            print(f"Transferring {file['id']}: {file['name']}")
            batch.add(
                drive.permissions().create(
                    fileId=file['id'],
                    body=user_permission,
                    transferOwnership=True
                )
            )
        input('Ready to transfer ownership?')
        batch.execute()


def move_file_to_shared_drive(drive, file_id, drive_id, drive_folder_id=None):
    print(f'Getting file parents for file {file_id}')
    file = drive.files().get(
        fileId=file_id,
        fields='parents'
    ).execute()

    print(f'Moving file {file_id} to shared drive {drive_id}')
    drive.files().update(
        fileId=file_id,
        addParents=drive_folder_id or drive_id,
        removeParents=','.join(file.get('parents')) or None,
        supportsAllDrives=True
    ).execute()


def move_folder_to_shared_drive(drive, source_email, drive_id, folder_id, folder_name, folder_parent_id=None):
    print(f'Moving folder {folder_name} ({folder_id}) to shared drive {drive_id}')

    # First get a list of all files/subfolders in the folder
    files = []
    request = drive.files().list(
        q=f"'{folder_id}' in parents",
        pageSize=1000,
        fields="files(id, name, parents, owners, mimeType, trashed)"
    )
    while request is not None:
        results = request.execute()
        files += results.get('files', [])
        request = drive.files().list_next(request, results)

    # Separate out all subfolders, and files owned by the source user
    subfolders = list(filter(lambda file: file['mimeType'] == 'application/vnd.google-apps.folder', files))
    files = list(filter(lambda file: file['mimeType'] != 'application/vnd.google-apps.folder' and
                    source_email in [owner['emailAddress'] for owner in file['owners']] and
                    not file['trashed'], files))

    # Then create an identically-named folder in the shared drive, if needed
    if folder_name == '[top level folder]':
        parent_id = folder_parent_id or drive_id
    else:
        folder_parent_id = folder_parent_id or drive_id
        request = drive.files().list(
            q=f"name = '{folder_name}' and '{drive_id}' in parents and mimeType = 'application/vnd.google-apps.folder'",
            pageSize=1000,
            fields="files(id)"
        ).execute()
        if request.get('files'):
            parent_id = request['files'][0]['id']
        else:
            drive_folder = drive.files().create(
                body={
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [folder_parent_id],
                },
                fields='id,parents,driveId',
                supportsAllDrives=True
            ).execute()
            parent_id = drive_folder['id']

    # Then move each file to the new folder
    chunks = [files[i:i + BATCH_SIZE] for i in range(0, len(files), BATCH_SIZE)]
    for chunk in chunks:
        batch = drive.new_batch_http_request(callback=batch_callback)
        for file in chunk:
            print(f"Transferring {file['id']}: {file['name']}")
            batch.add(
                drive.files().update(
                    fileId=file['id'],
                    addParents=parent_id,
                    removeParents=','.join(file.get('parents')) or None,
                    supportsAllDrives=True
                )
            )
        # input(f'Ready to transfer batch of {len(chunk)} files to shared drive?')
        batch.execute()

    # Finally recurse into each subfolder
    for subfolder in subfolders:
        move_folder_to_shared_drive(drive, source_email, drive_id, subfolder['id'], subfolder['name'], parent_id)


def main():
    parser = argparse.ArgumentParser(
        description='''The purpose of this script is to transfer a Google Drive file or folder (recursively) from
                       one user to another, or to a shared drive. Only docs/folders owned by the source user are
                       affected, all others are ignored. When moving files or folders to a shared drive, the source
                       user must be a member of the shared drive.
                    ''')
    parser.add_argument('--creds', required=True, help='Service account credentials file (e.g. credentials.json)')
    parser.add_argument('--folder', help='ID of folder to transfer or move')
    parser.add_argument('--file', help='ID of file to transfer or move')
    parser.add_argument('--files', help='Filename of text file that includes IDs of file to transfer or move')
    parser.add_argument('--source', required=True,
        help='Email address of person who currently owns the file(s) (e.g. alice@example.com)')
    parser.add_argument('--target-owner', help='Email address of person the file(s) ownership should be transferred to (e.g. bob@example.com)')
    parser.add_argument('--target-drive', help='ID of the shared drive to move file(s) to (NOTE: source user must be member of the drive)')
    parser.add_argument('--target-drive-folder', help='ID of the folder within the shared drive to move file(s) to')
    parser.add_argument('--verbose', action='store_true', help='Print all Google API requests to the console')
    parser.add_argument('--debug', action='store_true', help='Print all HTTP request and response headers and bodies to the console')
    args = parser.parse_args()

    if (args.folder and args.file) or (args.folder and args.files) or (args.file and args.files):
        print('Please specify either --folder or --file or --files, not more than one')
        exit(1)
    elif not args.folder and not args.file and not args.files:
        print('Please specify either --folder or --file or --files')
        exit(1)
    elif args.target_owner and args.target_drive:
        print('Please specify either --target-owner or --target-drive, not both')
        exit(1)
    elif not args.target_owner and not args.target_drive:
        print('Please specify either --target-owner or --target-drive')
        exit(1)

    if args.verbose:
        # https://github.com/googleapis/google-api-python-client/blob/main/docs/logging.md#log-level
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

    if args.debug:
        # https://github.com/googleapis/google-api-python-client/blob/main/docs/logging.md#http-traffic
        import httplib2
        httplib2.debuglevel = 4
        logger.setLevel(logging.DEBUG)

    drive = authorized_api('drive', 'v3', args.creds, args.source)

    if args.folder:
        if args.target_owner:
            all_folders = get_all_folders(drive, args.folder)
            all_files = get_all_files(drive, all_folders)

            reassign_ownership(drive, all_folders, args.source, args.target_owner)
            reassign_ownership(drive, all_files, args.source, args.target_owner)

        elif args.target_drive:
            move_folder_to_shared_drive(drive, args.source, args.target_drive, args.folder, '[top level folder]', args.target_drive_folder)

    elif args.file:
        if args.target_owner:
            reassign_ownership(drive, [{'id': args.file, 'name': '[chosen file]'}], args.source, args.target_owner)

        elif args.target_drive:
            move_file_to_shared_drive(drive, args.file, args.target_drive, args.target_drive_folder)
    
    elif args.files:
        with open(args.files, 'r') as f:
            file_ids = f.read().splitlines()

        if args.target_owner:
            reassign_ownership(drive, [{'id': file_id, 'name': '[chosen file]'} for file_id in file_ids], args.source, args.target_owner)

        elif args.target_drive:
            for file_id in file_ids:
                move_file_to_shared_drive(drive, file_id, args.target_drive, args.target_drive_folder)

    print('Transfer successful!')


if __name__ == '__main__':
    main()
