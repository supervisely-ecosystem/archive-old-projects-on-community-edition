import os, time
from distutils.util import strtobool
from datetime import datetime, timedelta
import supervisely as sly
from supervisely.io.fs import archive_directory, remove_dir, silent_remove
from dotenv import load_dotenv
import dropbox
import requests
from dropbox_content_hasher import StreamHasher, DropboxContentHasher


if sly.is_development():
    load_dotenv("local.env")
    load_dotenv(os.path.expanduser("~/supervisely.env"))


api = sly.Api.from_env()

days_storage = int(os.environ["modal.state.age"])
sleep_days = int(os.environ["modal.state.sleep"])
sleep_time = sleep_days * 86400
del_date = datetime.now() - timedelta(days=days_storage)
gb_format = 1024 * 1024 * 1024
storage_dir = sly.app.get_data_dir()

# variables for work with dropbox
chunk_size = 48 * 1024 * 1024
multiplicity = 4 * 1024 * 1024


def download_env_file_to_app_dir():
    initial_team_id = sly.env.team_id()
    team_files_env_file_path = os.environ["context.slyFile"]
    env_file_name = sly.env.file()
    app_env_file_path = os.path.join(storage_dir, env_file_name)
    api.file.download(initial_team_id, team_files_env_file_path, app_env_file_path)
    return app_env_file_path


def auth_to_dropbox():
    app_env_file_path = download_env_file_to_app_dir()
    sly.logger.info("Connecting to Dropbox...")
    load_dotenv(app_env_file_path)
    refresh_token = str(os.environ["refresh_token"])
    app_key = str(os.environ["app_key"])
    app_secret = str(os.environ["app_secret"])
    dbx = dropbox.Dropbox(
        oauth2_refresh_token=refresh_token, app_key=app_key, app_secret=app_secret
    )
    sly.logger.info("Connected successfully!")
    return dbx


def sort_by_date(projects_info):
    projects_to_del = {}
    for project_info in projects_info:
        project_date = project_info.updated_at
        project_date = datetime.strptime(project_date, "%Y-%m-%dT%H:%M:%S.%fZ")
        if project_date < del_date:
            projects_to_del[project_info.id] = project_info.name

    return projects_to_del


def compare_hashes(hash1, hash2):
    try:
        if hash1 == hash2:
            return True
        else:
            return False
    except (TypeError, ValueError):
        return False


def upload_as_session_to_dropbox(archive_path, name, chunk_size, dbx):
    with open(archive_path, "rb") as archive:
        file_size = os.path.getsize(archive_path)

        if chunk_size > file_size:
            chunk_size = (file_size // 2) // multiplicity * multiplicity

        name = str(name)
        upload_path = f"/{name}.tar"

        hasher = DropboxContentHasher()
        wrapped_archive = StreamHasher(archive, hasher)

        session_start_result = dbx.files_upload_session_start(
            wrapped_archive.read(chunk_size)
        )

        sly.logger.info(
            f"Uploading started for a project [ID: {name}] archive in stream mode"
        )

        session_id = session_start_result.session_id

        cursor = dropbox.files.UploadSessionCursor(
            session_id=session_id, offset=archive.tell()
        )

        commit = dropbox.files.CommitInfo(path=upload_path)

        while archive.tell() < file_size:
            if (file_size - archive.tell()) <= chunk_size:
                wrapped_archive = StreamHasher(archive, hasher)
                dbx.files_upload_session_finish(
                    wrapped_archive.read(chunk_size), cursor, commit
                )
                sly.logger.info(
                    f"Uploading finished for project [ID: '{name}'] archive "
                )
            else:
                try:
                    wrapped_archive = StreamHasher(archive, hasher)
                    dbx.files_upload_session_append_v2(
                        wrapped_archive.read(chunk_size), cursor
                    )
                    cursor.offset = archive.tell()
                except dropbox.exceptions.ApiError as e:
                    if e.error.is_conflict():
                        sly.logger.warning(
                            f"Session with ID: {session_id} expired. Starting new one"
                        )
                        session_id = e.error.get_conflict_value().session_id
                        cursor = dropbox.files.UploadSessionCursor(
                            session_id=session_id, offset=archive.tell()
                        )
                        wrapped_archive = StreamHasher(archive, hasher)
                        dbx.files_upload_session_append_v2(
                            wrapped_archive.read(chunk_size), cursor
                        )
                        cursor.offset = archive.tell()

        content_hash = dbx.files_get_metadata(upload_path).content_hash
        local_hash = hasher.hexdigest()
        hash_compare_results = compare_hashes(content_hash, local_hash)
        return upload_path, hash_compare_results


def remove_from_ecosystem(project_id, hash_compare_results, link_to_restore):
    if hash_compare_results:
        api.project.remove(
            project_id
        )  # replace with api call that deletes bypassing trash bin
        sly.logger.info(f"Project [ID: {project_id}] removed from Ecosystem")
    else:
        sly.logger.warning(
            f"Project [ID: {project_id}] will not be removed from Ecosystem due to hash mismatch. Please check the uploaded archive data at [{link_to_restore}]"
        )


def choose_teams():
    if not bool(strtobool(os.environ["modal.state.allTeams"])):
        team_id = os.environ["modal.state.teamId"]
        teams_infos = [api.team.get_info_by_id(team_id)]
    else:
        teams_infos = api.team.get_list()
    team_lists = []
    [team_lists.append(team[1]) for team in teams_infos]
    sly.logger.info(f"This {len(team_lists)} team(s) will be processed: {team_lists}")
    return teams_infos


def main():
    dbx = auth_to_dropbox()
    while True:
        sly.logger.info("Starting to archive old projects")
        teams_infos = choose_teams()
        for team_info in teams_infos:
            team_id = team_info[0]
            team_name = team_info[1]
            workspaces_info = api.workspace.get_list(team_id)
            for workspace_info in workspaces_info:
                workspace_id = workspace_info[0]
                workspace_name = workspace_info[1]
                projects_info = api.project.get_list(workspace_id)
                projects_to_del = sort_by_date(projects_info)
                sly.logger.info(
                    f"Checking old projects for [TEAM: {team_name}] [WORKSPACE: {workspace_name}]"
                )

                for project_id in projects_to_del.keys():
                    project_type = api.project.get_info_by_id(project_id).type
                    if project_type == "images":
                        dest_dir = os.path.join(storage_dir, str(project_id))
                        sly.logger.info(
                            f"Packing data for a project [ID: {project_id}] "
                        )
                        sly.Project.download(
                            api, project_id=project_id, dest_dir=dest_dir
                        )
                        archive_path = dest_dir + ".tar"
                        archive_directory(dest_dir, archive_path)
                        remove_dir(dest_dir)

                        while True:
                            try:
                                (
                                    link_to_restore,
                                    hash_compare_results,
                                ) = upload_as_session_to_dropbox(
                                    archive_path, project_id, chunk_size, dbx
                                )
                                break
                            except requests.exceptions.ConnectionError:
                                sly.logger.warning(
                                    f"Connection lost while uploading project [ID: {project_id}] archive"
                                )
                                time.sleep(5)

                        sly.logger.info(
                            f"Archived successfully [ID: {project_id}] [NAME: {projects_to_del[project_id]}] ! Link to restore: {link_to_restore}"
                        )

                        remove_from_ecosystem(
                            project_id, hash_compare_results, link_to_restore
                        )

                        silent_remove(archive_path)  # or move to backup?

                    # add processing for other types

        sly.logger.info(
            f"Task accomplished, standby mode activated. The next check will be in {sleep_days} day(s)"
        )
        time.sleep(sleep_time)


if __name__ == "__main__":
    sly.main_wrapper("main", main)
