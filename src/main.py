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
from dropbox_content_hasher import StreamHasher, DropboxContentHasher


if sly.is_development():
    load_dotenv("local.env")
    load_dotenv(os.path.expanduser("~/supervisely.env"))


api = sly.Api.from_env()

ALL_PROJECT_TYPES = ["images", "videos", "volumes", "point_clouds", "point_cloud_episodes"]
range_state = bool(strtobool(os.environ.get("modal.state.setRange")))
range_type = os.environ.get("modal.state.rangeType")
range_days = int(os.environ.get("modal.state.rangeDay"))
skip_exported = bool(strtobool(os.environ.get("modal.state.skipExported")))
sleep_days = int(os.environ.get("modal.state.sleep"))
batch_size = int(os.environ.get("modal.state.batchSize"))
sleep_time = sleep_days * 86400
storage_dir = sly.app.get_data_dir()

GB = 1024 * 1024 * 1024
MB = 1024 * 1024
chunk_size = 48 * MB
multiplicity = 4 * MB
max_archive_size = 348 * GB


def download_env_file():
    initial_team_id = sly.env.team_id()
    team_files_env_file_path = os.environ.get("context.slyFile")
    env_file_name = sly.env.file()
    app_env_file_path = os.path.join(storage_dir, env_file_name)
    api.file.download(initial_team_id, team_files_env_file_path, app_env_file_path)
    return app_env_file_path


def auth_to_dropbox():
    # app_env_file_path = download_env_file()
    sly.logger.info("Connecting to Dropbox...")
    # load_dotenv(app_env_file_path)
    load_dotenv("dropbox.env")
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


def choose_workspace():
    if not bool(strtobool(os.environ.get("modal.state.allWorkspaces"))):
        wspace_id = int(os.environ.get("modal.state.wSpaceId"))
    else:
        wspace_id = None
    return wspace_id


def choose_project_types():
    if not bool(strtobool(os.environ.get("modal.state.allPTypes"))):
        selected_project_types = os.environ.get("modal.state.types")
    else:
        selected_project_types = ALL_PROJECT_TYPES
    sly.logger.info(f"Processing Project type(s): {selected_project_types}")
    return selected_project_types


def choose_sorting():
    if not bool(strtobool(os.environ.get("modal.state.defSort"))):
        selected_sorting_type = os.environ.get("modal.state.sType")
        selected_sorting_order = os.environ.get("modal.state.sOrder")
        sly.logger.info(
            f"Processing projects sorted by type: {selected_sorting_type} and order: {selected_sorting_order}"
        )
    else:
        selected_sorting_type = None
        selected_sorting_order = None
    sly.logger.info(f"Processing projects sorted by default")
    return selected_sorting_type, selected_sorting_order


def get_project_infos(sort_type, sort_order):
    kwargs = {}
    if range_state and range_type == "From":
        kwargs["from_day"] = range_days
    if range_state and range_type == "To":
        kwargs["to_day"] = range_days
    if not skip_exported:
        kwargs["skip_exported"] = False

    if sort_type and sort_order:
        kwargs["sort"] = sort_type
        kwargs["sort_order"] = sort_order
    else:
        kwargs["sort"] = "updatedAt"
    project_infos = api.project.get_archivation_list(**kwargs)
    return project_infos


def download_project_by_type(project_type, api, project_id, temp_dir):
    project_classes = {
        "images": sly.Project,
        "videos": sly.VideoProject,
        "volumes": sly.VolumeProject,
        "point_clouds": sly.PointcloudProject,
        "point_cloud_episodes": sly.PointcloudEpisodeProject,
    }
    project_class = project_classes[project_type]

    if project_type in ["images", "point_clouds", "point_cloud_episodes"]:
        project_class.download(api, project_id=project_id, dest_dir=temp_dir, batch_size=batch_size)
    else:
        project_class.download(api, project_id=project_id, dest_dir=temp_dir)


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


def upload_via_session_to_dropbox(archive_path, chunk_size, dbx, destination):
    with open(archive_path, "rb") as archive:
        file_size = os.path.getsize(archive_path)

        if chunk_size >= file_size:
            # upload_chunk_size = (file_size // 2) // multiplicity * multiplicity
            chunk_size = file_size // 2
        name = archive_path.split("/")[-1]
        upload_path = f"{destination}/{name}"

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


def upload_archive_no_split(archive_path, chunk_size, dbx, destination_folder):
    while True:
        try:
            (
                upload_path,
                hash_compare_results,
            ) = upload_via_session_to_dropbox(
                archive_path,
                chunk_size,
                dbx,
                destination_folder,
            )
            link_to_restore = dbx.sharing_create_shared_link(upload_path).url
            break
        except requests.exceptions.ConnectionError:
            project_id = archive_path.split("/")[-1].split(".")[0]
            sly.logger.warning(
                f"Connection lost while uploading project [ID: {project_id}] archive"
            )
            time.sleep(5)
    return link_to_restore, hash_compare_results


def upload_archive_volumes(parts, chunk_size, dbx, destination_folder):
    sorted_parts = sorted(list(parts))
    hash_compare_results = list()
    for part in sorted_parts:
        _, hash_compare_result = upload_archive_no_split(part, chunk_size, dbx, destination_folder)
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


def set_project_archived(project_id, project_info, hash_compare_results, link_to_restore):
    if hash_compare_results:
        api.project.archive(project_id, link_to_restore)
        sly.logger.info(f"Project [ID: {project_id}] archived, data moved to Dropbox")
    else:
        if isinstance(link_to_restore, set):
            sly.logger.warning(
                f"Project [ID: {project_id}] data will not be moved to Dropbox due to hash mismatch."
            )
            for link in link_to_restore:
                sly.logger.warning(f"Please check the uploaded part of data at [{link}]")
        else:
            sly.logger.warning(
                f"Project [ID: {project_id}] data will not be moved to Dropbox due to hash mismatch. Please check the uploaded archive data at [{link_to_restore}]"
            )


def archive_project(project_id, project_info):
    sly.logger.info(" ")
    sly.logger.info(
        f"Archiving project [ID: {project_id}] size: {round(int(project_info.size) / GB, 1)} GB"
    )
    temp_dir = os.path.join(storage_dir, str(project_id))
    project_type = project_info.type
    download_project_by_type(project_type, api, project_id, temp_dir)
    archive_path = temp_dir + ".tar"

    if get_directory_size(temp_dir) >= max_archive_size:
        sly.logger.info(
            "The project takes up more space than the data transfer limits allow, so it will be split into several parts and placed in a separate Dropbox project folder."
        )
        tars_to_upload = set(archive_directory(temp_dir, archive_path, max_archive_size))
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
            chunk_size,
            dbx,
            destination_folder,
        )
        silent_remove(tars_to_upload)

    sly.logger.info(
        f"Uploaded successfully [ID: {project_id}] | Link to restore: {link_to_restore}"
    )

    set_project_archived(project_id, project_info, hash_compare_results, link_to_restore)


dbx = auth_to_dropbox()
destination_folder = create_folder_on_dropbox(dbx)


class TooManyExceptions(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


def main():
    while True:
        sort_type, sort_order = choose_sorting()
        project_infos = get_project_infos(sort_type, sort_order)
        workspace_id = choose_workspace()
        project_types = choose_project_types()
        task_id = api.task_id
        num_of_projects = len(project_infos)
        num_of_processed_projects = 0
        exception_counts = 0
        failed_projects = []

        slice_size = 10
        num_slices = (num_of_projects + slice_size - 1) // slice_size

        if num_of_projects != 0:
            with sly.tqdm_sly(total=num_of_projects, desc="Archiving projects") as pbar:
                for i in range(num_slices):
                    start = i * slice_size
                    end = start + slice_size
                    slice_data = project_infos[start:end]

                    random.shuffle(slice_data)

                    for project_info in slice_data:
                        if workspace_id:
                            if project_info.workspace_id != workspace_id:
                                pbar.update(1)
                                num_of_processed_projects += 1
                                sly.logger.info(
                                    f"Processed projects #{num_of_processed_projects} of {num_of_projects}"
                                )
                                continue

                        if project_info.type not in project_types:
                            pbar.update(1)
                            num_of_processed_projects += 1
                            sly.logger.info(
                                f"Processed projects #{num_of_processed_projects} of {num_of_projects}"
                            )
                            continue

                        if exception_counts > 3:
                            raise TooManyExceptions(
                                "The maximum number of missed projects in a row has been reached, apllication is interrupted"
                            )

                        exception_happened = False
                        custom_data = api.project.get_info_by_id(project_info.id).custom_data
                        if custom_data.get("archivation_status") in ("in_progress", "completed"):
                            ar_task_id = custom_data.get("archivation_task_id")
                            sly.logger.info(" ")
                            sly.logger.info(
                                f"Skipping project [ID: {project_info.id}]. Archived by App instance with ID: {ar_task_id}"
                            )
                        else:
                            custom_data["archivation_status"] = "in_progress"
                            custom_data["archivation_task_id"] = task_id
                            api.project.update_custom_data(project_info.id, custom_data)
                            try:
                                archive_project(project_info.id, project_info)
                            except Exception as e:
                                sly.logger.error(f"{e}")
                                sly.logger.warning(
                                    f"Process skipped for project [ID: {project_info.id}]. Status in custom data set to: failed"
                                )
                                failed_projects.append(project_info.id)
                                custom_data["archivation_status"] = "failed"
                                api.project.update_custom_data(project_info.id, custom_data)
                                exception_happened = True
                                exception_counts += 1
                            if not exception_happened:
                                exception_counts = 0
                                custom_data["archivation_status"] = "completed"
                                api.project.update_custom_data(project_info.id, custom_data)

                        num_of_processed_projects += 1
                        sly.logger.info(
                            f"Processed projects #{num_of_processed_projects} of {num_of_projects}"
                        )
                        pbar.update(1)

        sly.logger.info("Task accomplished, STANDBY mode activated.")
        sly.logger.info(f"The next check will be in {sleep_days} day(s)")

        if failed_projects:
            sly.logger.warning(f"FAILED PROJECTS: {failed_projects}")
            sly.logger.warning(f"Check them before the next run!")

        time.sleep(sleep_time)


if __name__ == "__main__":
    sly.main_wrapper("main", main)
