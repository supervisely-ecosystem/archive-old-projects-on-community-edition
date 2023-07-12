import os, time, random
from datetime import datetime, timedelta
from distutils.util import strtobool
import supervisely as sly
from supervisely.io.fs import (
    archive_directory,
    remove_dir,
    silent_remove,
    get_directory_size,
)
from dotenv import load_dotenv
import dropbox
import requests
import tarfile
from dropbox_content_hasher import StreamHasher, DropboxContentHasher


if sly.is_development():
    load_dotenv("local.env")
    load_dotenv(os.path.expanduser("~/supervisely.env"))


api = sly.Api.from_env()

ALL_PROJECT_TYPES = ["images", "videos", "volumes", "point_clouds", "point_cloud_episodes"]
days_storage = int(os.environ["modal.state.age"])
sleep_days = int(os.environ["modal.state.sleep"])
sleep_time = sleep_days * 86400
del_date = datetime.now() - timedelta(days=days_storage)
storage_dir = sly.app.get_data_dir()

GB = 1024 * 1024 * 1024
MB = 1024 * 1024
chunk_size = 48 * MB
multiplicity = 4 * MB
max_archive_size = 348 * GB


def download_env_file():
    initial_team_id = sly.env.team_id()
    team_files_env_file_path = os.environ["context.slyFile"]
    env_file_name = sly.env.file()
    app_env_file_path = os.path.join(storage_dir, env_file_name)
    api.file.download(initial_team_id, team_files_env_file_path, app_env_file_path)
    return app_env_file_path


def auth_to_dropbox():
    app_env_file_path = download_env_file()
    sly.logger.info("Connecting to Dropbox...")
    load_dotenv(app_env_file_path)
    # load_dotenv("dropbox.env")
    try:
        refresh_token = str(os.environ["refresh_token"])
        app_key = str(os.environ["app_key"])
        app_secret = str(os.environ["app_secret"])
        dbx_user_id = str(os.environ["dbx_user_id"]) if "dbx_user_id" in os.environ else None

        for key in (refresh_token, app_key, app_secret):
            if key == "":
                raise ValueError(f"ERROR: {app_env_file_path} file contains empty value(s)")
    except KeyError as error:
        raise KeyError(
            f"ERROR: {app_env_file_path} file does not contain the necessary data: [{error.args[0]}]"
        )

    try:
        if dbx_user_id:
            dbx = dropbox.Dropbox(
                headers={"Dropbox-API-Select-User": dbx_user_id},
                oauth2_refresh_token=refresh_token,
                app_key=app_key,
                app_secret=app_secret,
            )
            member = " as Business Team member"
        else:
            dbx = dropbox.Dropbox(
                oauth2_refresh_token=refresh_token, app_key=app_key, app_secret=app_secret
            )
            member = " as Basic user"
    except dropbox.dropbox_client.BadInputException as error:
        raise dropbox.dropbox_client.BadInputException(
            message=f"ERROR: {error.error}", request_id=error.request_id
        )

    try:
        dbx.check_user()
        sly.logger.info(f"Connected successfully{member}!")
    except dropbox.exceptions.BadInputError as error:
        raise ValueError(
            error.args[2], f"Authorisation unsuccessful. Check values in {app_env_file_path}"
        )

    return dbx


def choose_teams():
    if not bool(strtobool(os.environ["modal.state.allTeams"])):
        team_id = os.environ["modal.state.teamId"]
        teams_infos = [api.team.get_info_by_id(team_id)]
    else:
        teams_infos = api.team.get_list()
    team_lists = []
    [team_lists.append(team[1]) for team in teams_infos]
    sly.logger.info(f"Processing {len(team_lists)} team(s) : {team_lists}")
    return teams_infos


def choose_project_types():
    if not bool(strtobool(os.environ["modal.state.allPTypes"])):
        selected_project_types = os.environ["modal.state.types"]
    else:
        selected_project_types = ALL_PROJECT_TYPES
    sly.logger.info(f"Processing Project type(s): {selected_project_types}")
    return selected_project_types


def sort_by_date(projects_info):
    projects_to_archive = {}
    for project_info in projects_info:
        project_date = project_info.updated_at
        project_date = datetime.strptime(project_date, "%Y-%m-%dT%H:%M:%S.%fZ")
        if project_date < del_date:
            projects_to_archive[project_info.id] = project_info.name

    return projects_to_archive


def download_project_by_type(project_type, api, project_id, temp_dir):
    if project_type == "images":
        sly.Project.download(api, project_id=project_id, dest_dir=temp_dir)
    elif project_type == "videos":
        sly.VideoProject.download(api, project_id=project_id, dest_dir=temp_dir)
    elif project_type == "volumes":
        sly.VolumeProject.download(api, project_id=project_id, dest_dir=temp_dir)
    elif project_type == "point_clouds":
        sly.PointcloudProject.download(api, project_id=project_id, dest_dir=temp_dir)
    elif project_type == "point_cloud_episodes":
        sly.PointcloudEpisodeProject.download(api, project_id=project_id, dest_dir=temp_dir)


def is_project_archived(project_info):
    try:
        project_info.backup_archive["exportedAt"]
        return True
    except:
        return False


def create_multivolume_archive(temp_dir, storage_dir, max_archive_size):
    file_name = temp_dir.split("/")[-1]
    files = []
    current_archive_files = []
    archive_names = set()
    part_num = 0

    for dirpath, _, filenames in os.walk(temp_dir):
        for filename in filenames:
            files.append(os.path.join(dirpath, filename))

    files.sort(key=lambda f: os.path.getsize(f))

    for file in files:
        if (
            sum(os.path.getsize(f) for f in current_archive_files) + os.path.getsize(file)
            > max_archive_size
        ):
            part_num += 1
            archive_name = f"{storage_dir}/{file_name}.part{part_num:03}.tar"
            archive_names.add(archive_name)
            with tarfile.open(archive_name, "w") as archive:
                for f in current_archive_files:
                    archive.add(f, f.replace(temp_dir, ""))
            current_archive_files = []

        current_archive_files.append(file)

    part_num += 1
    archive_name = f"{storage_dir}/{file_name}.part{part_num:03}.tar"
    archive_names.add(archive_name)
    with tarfile.open(archive_name, "w") as archive:
        for f in current_archive_files:
            archive.add(f, f.replace(temp_dir, ""))
    return archive_names


def create_folder_on_dropbox(dbx: dropbox.Dropbox):
    task_id = os.getenv("TASK_ID")
    parent = "/supervisely_project_archives"

    try:
        dbx.files_list_folder(parent)
        dir_exists = True
    except dropbox.exceptions.ApiError as e:
        if isinstance(e.error, dropbox.files.ListFolderError):
            dir_exists = False
        else:
            sly.logger.warning(f"API error: {e}")

    if dir_exists is False:
        dbx.files_create_folder_v2(parent)

    folder_path = f"{parent}/archive_{task_id}"

    try:
        sly.logger.info(f"Creating folder [{folder_path[1:]}] on Dropbox")
        dbx.files_create_folder_v2(folder_path)
    except dropbox.exceptions.ApiError as e:
        if e.error.get_path().is_conflict():
            sly.logger.info(f"Folder [{folder_path[1:]}] already exists")
        else:
            sly.logger.warning(f"Error occured while creating [{folder_path[1:]}] folder")
    return folder_path


def upload_via_session_to_dropbox(archive_path, name, chunk_size, dbx, destination):
    with open(archive_path, "rb") as archive:
        file_size = os.path.getsize(archive_path)

        if chunk_size >= file_size:
            # upload_chunk_size = (file_size // 2) // multiplicity * multiplicity
            chunk_size = file_size // 2
        name = str(name)
        upload_path = f"{destination}/{name}.tar"

        hasher = DropboxContentHasher()
        wrapped_archive = StreamHasher(archive, hasher)

        session_start_result = dbx.files_upload_session_start(wrapped_archive.read(chunk_size))

        sly.logger.info(f"Uploading started for [{name}] ")

        session_id = session_start_result.session_id

        cursor = dropbox.files.UploadSessionCursor(session_id=session_id, offset=archive.tell())

        commit = dropbox.files.CommitInfo(path=upload_path)

        while archive.tell() < file_size:
            if (file_size - archive.tell()) <= chunk_size:
                wrapped_archive = StreamHasher(archive, hasher)
                dbx.files_upload_session_finish(wrapped_archive.read(chunk_size), cursor, commit)
                sly.logger.info(f"Uploading finished for [{name}]")
            else:
                try:
                    wrapped_archive = StreamHasher(archive, hasher)
                    dbx.files_upload_session_append_v2(wrapped_archive.read(chunk_size), cursor)
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
                        dbx.files_upload_session_append_v2(wrapped_archive.read(chunk_size), cursor)
                        cursor.offset = archive.tell()

        content_hash = dbx.files_get_metadata(upload_path).content_hash
        local_hash = hasher.hexdigest()
        hash_compare_results = compare_hashes(content_hash, local_hash)
        return upload_path, hash_compare_results


def upload_archive_no_split(archive_path, project_id, chunk_size, dbx, destination_folder):
    while True:
        try:
            (
                upload_path,
                hash_compare_results,
            ) = upload_via_session_to_dropbox(
                archive_path,
                project_id,
                chunk_size,
                dbx,
                destination_folder,
            )
            link_to_restore = dbx.sharing_create_shared_link(upload_path).url
            break
        except requests.exceptions.ConnectionError:
            sly.logger.warning(
                f"Connection lost while uploading project [ID: {project_id}] archive"
            )
            time.sleep(5)
    return link_to_restore, hash_compare_results


def upload_archive_volumes(parts, chunk_size, dbx, destination_folder):
    sorted_parts = sorted(list(parts))
    hash_compare_results = list()
    for part in sorted_parts:
        part_name = part.split("/")[-1].replace(".tar", "")
        _, hash_compare_result = upload_archive_no_split(
            part, part_name, chunk_size, dbx, destination_folder
        )
        hash_compare_results.append(hash_compare_result)
    hash_compare_results = all(hash_compare_results)
    link_to_restore = dbx.sharing_create_shared_link(destination_folder).url
    return link_to_restore, hash_compare_results


def compare_hashes(hash1, hash2):
    try:
        if hash1 == hash2:
            return True
        else:
            return False
    except (TypeError, ValueError):
        return False


def set_project_archived(project_id, hash_compare_results, link_to_restore):
    
    if is_project_archived(api.project.get_info_by_id(project_id)):
        sly.logger.warning(f"Skip adding URL for project {project_id}, this project is already archived")
        shared_link_metadata = dbx.sharing_get_shared_link_metadata(link_to_restore)
        dbx.files_delete_v2(shared_link_metadata.path_lower)
        return
    if hash_compare_results:
        api.project.archive(project_id, link_to_restore)
        sly.logger.info(f"Project [ID: {project_id}] archived, data removed from Ecosystem")
    else:
        if isinstance(link_to_restore, set):
            sly.logger.warning(
                f"Project [ID: {project_id}] data will not be removed from Ecosystem due to hash mismatch."
            )
            for link in link_to_restore:
                sly.logger.warning(f"Please check the uploaded part of data at [{link}]")
        else:
            sly.logger.warning(
                f"Project [ID: {project_id}] data will not be removed from Ecosystem due to hash mismatch. Please check the uploaded archive data at [{link_to_restore}]"
            )


def collect_project_ids():
    choosen_projects = []
    teams_infos = choose_teams()
    selected_project_types = choose_project_types()
    for team_info in teams_infos:
        workspaces_info = api.workspace.get_list(team_info.id)
        for workspace_info in workspaces_info:
            projects_info = api.project.get_list(workspace_info.id)
            projects_to_del = sort_by_date(projects_info)
            for project_id in projects_to_del.keys():
                project_info = api.project.get_info_by_id(project_id)
                project_archived = is_project_archived(project_info)
                if project_info.type in selected_project_types and not project_archived:
                    choosen_projects.append(project_id)
    return choosen_projects


def archive_project(project_id):
    sly.logger.info(f"Starting to archive project [ID: {project_id}] ")
    temp_dir = os.path.join(storage_dir, str(project_id))
    temp_dir = temp_dir.replace("\\", "/")    
    project_type = api.project.get_info_by_id(project_id).type
    download_project_by_type(project_type, api, project_id, temp_dir)
    archive_path = temp_dir + ".tar" 
        
    if get_directory_size(temp_dir) >= max_archive_size:
        sly.logger.info(
            "The project takes up more space than the data transfer limits allow, so it will be split into several parts and placed in a separate Dropbox project folder."
        )
        tars_to_upload = create_multivolume_archive(temp_dir, storage_dir, max_archive_size)
        sly.logger.info(f"The number of archives: {len(tars_to_upload)}")
    else:
        archive_directory(temp_dir, archive_path)
        tars_to_upload = archive_path

    remove_dir(temp_dir)

    if isinstance(tars_to_upload, set):
        destination_folder_for_project = f"{destination_folder}/{project_id}"
        dbx.files_create_folder_v2(destination_folder_for_project)
        sly.logger.info(f"A nested folder has been created with the name: {project_id}")
        link_to_restore, hash_compare_results = upload_archive_volumes(
            tars_to_upload,
            chunk_size,
            dbx,
            destination_folder_for_project,
        )
        for tar in tars_to_upload:
            silent_remove(tar)
    else:
        link_to_restore, hash_compare_results = upload_archive_no_split(
            tars_to_upload,
            project_id,
            chunk_size,
            dbx,
            destination_folder,
        )
        silent_remove(tars_to_upload)

    sly.logger.info(
        f"Uploaded successfully [ID: {project_id}] | Link to restore: {link_to_restore}"
    )

    set_project_archived(project_id, hash_compare_results, link_to_restore)


dbx = auth_to_dropbox()
destination_folder = create_folder_on_dropbox(dbx)


def main():
    while True:
        project_ids = collect_project_ids()        
        random.shuffle(project_ids)
        skipped_projects = []
        task_id = api.task_id
        if len(project_ids) != 0:
            with sly.tqdm_sly(total=len(project_ids), desc="Archiving projects") as pbar:
                for project_id in project_ids:
                    try:                        
                        custom_data = api.project.get_info_by_id(project_id).custom_data
                        if custom_data.get("archivation_status") == "in_progress":
                            ar_task_id = custom_data.get("archivation_task_id")
                            sly.logger.info(
                                f"Skipping project {project_id} that is currently being archived by another App instance with ID: {ar_task_id}"
                            )
                            pbar.update(1)
                            continue
                        custom_data["archivation_status"] = "in_progress"
                        custom_data["archivation_task_id"] = task_id
                        api.project.update_custom_data(project_id, custom_data)
                        archive_project(project_id)
                        custom_data["archivation_status"] = "completed"
                        api.project.update_custom_data(project_id, custom_data)
                    except Exception as e:                        
                        sly.logger.error(f'{e}')
                        sly.logger.warning(f'Process skipped for Project with ID: {project_id}')
                        skipped_projects.append(project_id)
                        custom_data["archivation_status"] = "failed"
                        api.project.update_custom_data(project_id, custom_data)
                    pbar.update(1)

        sly.logger.info(
            f"Task accomplished, standby mode activated. The next check will be in {sleep_days} day(s)"
        )
        if skipped_projects:
            sly.logger.warning(f"Check this list of Porjects that failed to archive before the next run: {skipped_projects}")            
        time.sleep(sleep_time)


if __name__ == "__main__":
    sly.main_wrapper("main", main)
