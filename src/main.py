import os, time
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


def auth_to_dropbox():
    sly.logger.info("Connecting to Dropbox...")
    initial_team_id = sly.env.team_id()
    local_env_path = os.path.join(storage_dir, "dropbox.env")
    remote_env_path = os.environ["context.slyFile"]
    api.file.download(initial_team_id, remote_env_path, local_env_path)
    load_dotenv(local_env_path)
    refresh_token = str(os.environ["refresh_token"])
    app_key = str(os.environ["app_key"])
    app_secret = str(os.environ["app_secret"])
    dbx = dropbox.Dropbox(
        oauth2_refresh_token=refresh_token, app_key=app_key, app_secret=app_secret
    )
    sly.logger.info("Successfully connected")
    return dbx


def sort_by_date(projects_info):
    projects_to_del = {}
    for project_info in projects_info:
        project_date = project_info.updated_at
        project_date = datetime.strptime(project_date, "%Y-%m-%dT%H:%M:%S.%fZ")
        if project_date < del_date:
            projects_to_del[project_info.id] = project_info.name

    return projects_to_del


def upload_as_session_to_dropbox(archive_path, name, chunk_size, dbx):
    with open(archive_path, "rb") as archive:
        file_size = os.path.getsize(archive_path)

        if chunk_size > file_size:
            chunk_size = (file_size // 2) // multiplicity * multiplicity

        name = str(name)
        upload_path = "/{}.tar".format(name)

        hasher = DropboxContentHasher()
        wrapped_archive = StreamHasher(archive, hasher)

        session_start_result = dbx.files_upload_session_start(
            wrapped_archive.read(chunk_size)
        )

        sly.logger.info("Uploading archive '{}' in stream mode started".format(name))

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
                sly.logger.info("Uploading archive '{}' finished".format(name))
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
                            "Session with ID:{} expired. Starting new one".format(
                                session_id
                            )
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

        conten_thash = dbx.files_get_metadata(upload_path).content_hash
        local_hash = hasher.hexdigest()
        assert conten_thash == local_hash

        return upload_path


def main():
    dbx = auth_to_dropbox()
    while True:
        sly.logger.info("Start archiving old projects")
        teams_infos = api.team.get_list()
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
                    "Check old projects for {} team, {} workspace".format(
                        team_name, workspace_name
                    )
                )

                for project_id in projects_to_del.keys():
                    project_type = api.project.get_info_by_id(project_id).type
                    if project_type == "images":
                        dest_dir = os.path.join(storage_dir, str(project_id))
                        sly.logger.info(
                            "Start downloading data for project ID: {} ".format(
                                project_id
                            )
                        )
                        sly.Project.download(
                            api, project_id=project_id, dest_dir=dest_dir
                        )
                        archive_path = dest_dir + ".tar"
                        archive_directory(dest_dir, archive_path)
                        remove_dir(dest_dir)

                        while True:
                            try:
                                link_to_restore = upload_as_session_to_dropbox(
                                    archive_path, project_id, chunk_size, dbx
                                )
                                break
                            except requests.exceptions.ConnectionError:
                                sly.logger.warning(
                                    "Connection lost while uploading archive {}".format(
                                        project_id
                                    )
                                )
                                time.sleep(5)

                        sly.logger.info(
                            "Project with name {} was archived, link to restore: {}".format(
                                projects_to_del[project_id], link_to_restore
                            )
                        )

                        api.project.remove(
                            project_id
                        )  # replace with api call that deletes bypassing trash bin

                        silent_remove(archive_path)  # or move to backup?

                    # add processing for other types

        sly.logger.info(
            "Task accomplished, standby mode activated. The next check will be in {} day(s)".format(
                sleep_days
            )
        )
        time.sleep(sleep_time)


if __name__ == "__main__":
    sly.main_wrapper("main", main)
