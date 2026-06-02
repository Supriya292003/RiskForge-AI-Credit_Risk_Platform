import os
from pathlib import Path

def is_running_in_docker() -> bool:
    """Checks if the application is currently running inside a Docker container."""
    # Check /.dockerenv file or check /proc/1/cgroup contents
    if os.path.exists('/.dockerenv'):
        return True
    
    try:
        with open('/proc/1/cgroup', 'rt') as f:
            return 'docker' in f.read()
    except Exception:
        pass
        
    return False

def resolve_data_path(base_dir: Path, env_var_name: str, default_folder_name: str) -> Path:
    """
    Resolves data paths dynamically depending on whether running in Docker or locally.
    In Docker, paths are typically mounted at '/data' or similar absolute paths.
    """
    if is_running_in_docker():
        # In Docker, we check if environment specifies an absolute path, or default to mounted path
        env_val = os.getenv(env_var_name)
        if env_val and os.path.isabs(env_val):
            return Path(env_val)
        # Default mounted folder under docker root
        docker_mounted_path = Path(f"/{default_folder_name}")
        if docker_mounted_path.exists():
            return docker_mounted_path
            
    return base_dir / os.getenv(env_var_name, default_folder_name)
