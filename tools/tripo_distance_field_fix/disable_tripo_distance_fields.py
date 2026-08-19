"""Disable mesh distance-field generation for imported tripo_node meshes.

Run this script inside the Unreal Engine 4.26 editor. Before running it, set
`r.GenerateMeshDistanceFields=False` in the project's DefaultEngine.ini and
restart the editor. The safety check below refuses to load the meshes while
global distance-field generation is still enabled.
"""

import unreal


ROOT = "/Game/1a/Static/Terrain/1a"
NAME_TOKEN = "tripo_node"

# First run: leave this True to print the targets without modifying assets.
# After checking the Output Log, change it to False and run the script again.
DRY_RUN = False


def main():
    distance_fields_enabled = unreal.SystemLibrary.get_console_variable_int_value(
        "r.GenerateMeshDistanceFields"
    )
    if distance_fields_enabled != 0:
        raise RuntimeError(
            "Safety stop: r.GenerateMeshDistanceFields is enabled. "
            "Set it to False in DefaultEngine.ini and restart Unreal Editor "
            "before running this script."
        )

    asset_paths = unreal.EditorAssetLibrary.list_assets(
        ROOT,
        recursive=True,
        include_folder=False,
    )
    targets = [path for path in asset_paths if NAME_TOKEN in path.lower()]

    unreal.log(
        "Tripo distance-field batch: found {} target assets (dry_run={})".format(
            len(targets), DRY_RUN
        )
    )

    changed = 0
    skipped = 0
    failed = []

    for index, path in enumerate(targets, 1):
        try:
            asset = unreal.EditorAssetLibrary.load_asset(path)
            if not isinstance(asset, unreal.StaticMesh):
                skipped += 1
                unreal.log_warning(
                    "[{}/{}] Skipped non-StaticMesh: {}".format(
                        index, len(targets), path
                    )
                )
                continue

            settings = unreal.EditorStaticMeshLibrary.get_lod_build_settings(asset, 0)
            old_scale = settings.get_editor_property(
                "distance_field_resolution_scale"
            )

            unreal.log(
                "[{}/{}] {}: {} -> 0.0{}".format(
                    index,
                    len(targets),
                    path,
                    old_scale,
                    " (dry run)" if DRY_RUN else "",
                )
            )

            if DRY_RUN or old_scale == 0.0:
                continue

            settings.set_editor_property("distance_field_resolution_scale", 0.0)
            unreal.EditorStaticMeshLibrary.set_lod_build_settings(asset, 0, settings)

            # Save after every mesh so completed work survives an interruption.
            saved = unreal.EditorAssetLibrary.save_loaded_asset(
                asset,
                only_if_is_dirty=False,
            )
            if not saved:
                raise RuntimeError("save_loaded_asset returned False")

            changed += 1

        except Exception as exc:
            failed.append((path, str(exc)))
            unreal.log_error("FAILED {}: {}".format(path, exc))

    unreal.log(
        "Tripo distance-field batch finished: targets={}, changed={}, "
        "skipped={}, failed={}, dry_run={}".format(
            len(targets), changed, skipped, len(failed), DRY_RUN
        )
    )

    for path, error in failed:
        unreal.log_error("FAILED {}: {}".format(path, error))


main()
