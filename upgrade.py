#!/usr/bin/env python3
"""
ArchivesSpace Upgrade Script

This script upgrades ArchivesSpace by:
1. Downloading the latest release
2. Updating configuration files
3. Running the restore script
4. Setting up the new version with Docker

Usage: sudo python3 upgrade.py [--rebuild-solr]
"""

import os
import sys
import subprocess
import shutil
import zipfile
import re
import argparse
from pathlib import Path
from datetime import datetime


def check_root():
    """Check if script is running as root."""
    if os.geteuid() != 0:
        print("😵 SCRIPT MUST BE RUN AS ROOT (to modify /opt files)")
        print("EXAMPLE: sudo python3 upgrade.py [--rebuild-solr]")
        sys.exit(1)


def load_env_file(env_path=".env"):
    """Load environment variables from .env file."""
    if not os.path.exists(env_path):
        print(".env file not found")
        sys.exit(1)
    
    env_vars = {}
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key] = value
                os.environ[key] = value
    
    return env_vars


def download_and_extract_release(tag):
    """Download and extract ArchivesSpace release."""
    url = f"https://github.com/archivesspace/archivesspace/releases/download/{tag}/archivesspace-docker-{tag}.zip"
    zip_filename = f"archivesspace-docker-{tag}.zip"
    
    print(f"Downloading {url}...")
    subprocess.run(["curl", "-L", "-O", url], check=True)
    
    print(f"Extracting {zip_filename}...")
    with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
        zip_ref.extractall()
    
    os.remove(zip_filename)
    print(f"Removed {zip_filename}")


def replace_config_value(key, old_value, new_value, file_path):
    """Replace configuration values in files (both .env and .rb formats)."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    if file_path.endswith('.rb'):
        # For Ruby config files
        # Escape special regex characters in key
        escaped_key = re.escape(key)
        # Escape special regex characters in old and new values
        escaped_old = re.escape(old_value)
        escaped_new = new_value.replace('\\', '\\\\').replace('&', '\\&')
        
        # Pattern: find lines containing the key, then substitute old with new
        pattern = f"({escaped_key}.*?){escaped_old}"
        content = re.sub(pattern, f"\\1{escaped_new}", content)
    else:
        # .env file format: KEY=value
        pattern = f"^{re.escape(key)}=.*{re.escape(old_value)}.*"
        replacement = f"{key}={new_value}"
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    with open(file_path, 'w') as f:
        f.write(content)


def run_restore_script():
    """Run the restore script with --upgrade flag."""
    print("Running restore script...")
    subprocess.run(["python3", "restore.py", "--upgrade"], check=True)


def prepare_database_backup(db_name):
    """Prepare database backup for the upgrade."""
    # Get current date (local time should be Pacific timezone on the server)
    datestamp = datetime.now().strftime('%Y-%m-%d')
    
    backup_path = f"backups/{db_name}-{datestamp}.sql.gz"
    sql_path = f"backups/{db_name}-{datestamp}.sql"
    
    print(f"Extracting database backup: {backup_path}")
    subprocess.run(["gunzip", "-k", backup_path], check=True)
    
    # Move to archivesspace sql directory
    sql_dest = "archivesspace/sql"
    os.makedirs(sql_dest, exist_ok=True)
    shutil.move(sql_path, f"{sql_dest}/{db_name}-{datestamp}.sql")
    print(f"Moved database backup to {sql_dest}")


def setup_archivesspace_directory(tag):
    """Set up the ArchivesSpace directory structure."""
    old_dir = f"archivesspace-docker-{tag}"
    new_dir = "archivesspace"
    
    # Remove old directory if it exists
    if os.path.exists(old_dir):
        shutil.rmtree(old_dir)
        print(f"Removed existing {old_dir}")
    
    # Rename archivesspace to the versioned directory name
    if os.path.exists(new_dir):
        shutil.move(new_dir, old_dir)
        print(f"Renamed {new_dir} to {old_dir}")


def docker_operations(tag, rebuild_solr=False):
    """Handle Docker operations for the upgrade."""
    opt_path = Path("/opt/archivesspace")
    
    # Change to /opt/archivesspace and bring down services
    print("Stopping ArchivesSpace services...")
    os.chdir(opt_path)
    subprocess.run(["docker", "compose", "down"], check=True)
    
    if rebuild_solr:
        print("Removing Docker volumes for fresh Solr rebuild...")
        subprocess.run([
            "docker", "volume", "rm", 
            "archivesspace_app-data", 
            "archivesspace_solr-data"
        ], check=False)  # Don't fail if volumes don't exist
    
    # Return to script directory
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)
    
    # Create symlink to new version
    target_dir = script_dir / f"archivesspace-docker-{tag}"
    if opt_path.is_symlink() or opt_path.exists():
        opt_path.unlink(missing_ok=True)
    
    opt_path.symlink_to(target_dir)
    print(f"Created symlink: {opt_path} -> {target_dir}")
    
    # Start services
    print("Starting ArchivesSpace services...")
    os.chdir(opt_path)
    subprocess.run(["docker", "compose", "pull"], check=True)
    subprocess.run([
        "docker", "compose", "up", "-d", 
        "--build", "--force-recreate"
    ], check=True)


def main():
    """Main function to orchestrate the upgrade process."""
    parser = argparse.ArgumentParser(description="Upgrade ArchivesSpace")
    parser.add_argument("--rebuild-solr", action="store_true", 
                       help="Rebuild Solr data volumes")
    args = parser.parse_args()
    
    # Check if running as root
    check_root()
    
    # Load environment variables
    env_vars = load_env_file()
    tag = env_vars.get('TAG')
    db_name = env_vars.get('DB')
    domain = env_vars.get('DOMAIN')
    
    if not all([tag, db_name, domain]):
        print("Error: TAG, DB, and DOMAIN must be set in .env file")
        sys.exit(1)
    
    try:
        # Download and extract release
        download_and_extract_release(tag)
        
        # Replace configuration values
        print("Updating configuration files...")
        replace_config_value("MYSQL_DATABASE", "archivesspace", db_name, ".env")
        replace_config_value("AppConfig[:db_url]", "archivesspace", db_name, "config/config.rb")
        replace_config_value("AppConfig[:oai_proxy_url]", "localhost", domain, "config/config.rb")
        replace_config_value("AppConfig[:frontend_proxy_url]", "localhost", domain, "config/config.rb")
        replace_config_value("AppConfig[:public_proxy_url]", "localhost", domain, "config/config.rb")
        
        # Run restore script
        run_restore_script()
        
        # Prepare database backup
        prepare_database_backup(db_name)
        
        # Setup directory structure
        setup_archivesspace_directory(tag)
        
        # Handle Docker operations
        docker_operations(tag, args.rebuild_solr)
        
        print("🎉 Upgrade complete! ArchivesSpace is now running with the latest version. It may take a few minutes to become available.")
        
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
