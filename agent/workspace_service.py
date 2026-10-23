"""Alias for agent.workspace module compatibility."""

try:
    from .workspace import *  # noqa: F401, F403
    from .workspace import (  # noqa: F401
        MAX_EDITABLE_FILE_CHARS,
        WorkspaceBinaryFileError,
        WorkspaceConflictError,
        WorkspaceValidationError,
        build_workspace_zip,
        cleanup_expired_sessions,
        create_folder,
        create_session,
        delete_path,
        delete_session,
        list_flat_text_files,
        list_tree,
        read_text_file,
        rename_path,
        resolve_workspace_session,
        touch_session,
        workspace_context,
        write_text_file,
    )
except ImportError:  # pragma: no cover
    from workspace import *  # noqa: F401, F403
    from workspace import (  # noqa: F401
        MAX_EDITABLE_FILE_CHARS,
        WorkspaceBinaryFileError,
        WorkspaceConflictError,
        WorkspaceValidationError,
        build_workspace_zip,
        cleanup_expired_sessions,
        create_folder,
        create_session,
        delete_path,
        delete_session,
        list_flat_text_files,
        list_tree,
        read_text_file,
        rename_path,
        resolve_workspace_session,
        touch_session,
        workspace_context,
        write_text_file,
    )
