#!/usr/bin/env python3
"""
ArchivesSpace Database Restore Script

This script downloads database backups from S3 and restores them to ArchivesSpace.

Usage: python3 restore.py [<ISO DATE>] [--upgrade]
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import argparse


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


def get_datestamp(date_arg=None):
    """Get the datestamp for the backup file."""
    if date_arg and date_arg != "--upgrade":
        return date_arg
    else:
        # Use local time which should be Pacific timezone on the server
        return datetime.now().strftime('%Y-%m-%d')


def download_backup_from_s3(bucket, db_name, datestamp, tmp_dir):
    """Download backup from S3 if it doesn't exist locally."""
    script_dir = Path(__file__).parent.absolute()
    backups_dir = script_dir / "backups"
    backups_dir.mkdir(exist_ok=True)
    
    local_filepath = backups_dir / f"{db_name}-{datestamp}.sql.gz"
    
    if not local_filepath.exists():
        print(f"Downloading backup for {datestamp}...")
        s3_path = f"s3://{bucket}/{db_name}-{datestamp}.sql.gz"
        tmp_file = Path(tmp_dir) / f"{db_name}-{datestamp}.sql.gz"
        
        try:
            subprocess.run([
                "/usr/local/bin/aws", "s3", "cp", s3_path, str(tmp_file), "--no-progress"
            ], check=True)
        except subprocess.CalledProcessError:
            print("😵 FAILED TO DOWNLOAD BACKUP DATABASE FROM S3.")
            sys.exit(1)
        
        # Decompress the file
        print("Decompressing backup file...")
        subprocess.run(["gunzip", "-k", str(tmp_file)], check=True)
        
        return tmp_file, Path(tmp_dir) / f"{db_name}-{datestamp}.sql"
    else:
        print(f"Using existing backup: {local_filepath}")
        return local_filepath, None


def restore_database(db_name, datestamp, tmp_dir, upgrade_mode=False):
    """Restore the database from backup."""
    if upgrade_mode:
        print("Running in upgrade mode - skipping database restore")
        return
    
    sql_file = Path(tmp_dir) / f"{db_name}-{datestamp}.sql"
    
    print("Restoring database...")
    # Change to /opt/archivesspace for docker commands
    original_dir = os.getcwd()
    try:
        os.chdir("/opt/archivesspace")
        subprocess.run([
            "docker", "exec", "mysql", "mysql", 
            "-uas", "-pas123", "archivesspace"
        ], stdin=open(sql_file, 'r'), check=True)
    finally:
        os.chdir(original_dir)


def reset_admin_password():
    """Reset the admin password."""
    print("Resetting admin password...")
    original_dir = os.getcwd()
    try:
        os.chdir("/opt/archivesspace")
        subprocess.run([
            "docker", "exec", "archivesspace", 
            "/archivesspace/scripts/password-reset.sh", "admin", "admin"
        ], check=True)
    finally:
        os.chdir(original_dir)


def reindex_data():
    """Perform soft reindex by removing indexer state files."""
    print("Performing soft reindex...")
    original_dir = os.getcwd()
    try:
        os.chdir("/opt/archivesspace")
        subprocess.run([
            "docker", "exec", "archivesspace", 
            "rm", "-f", "/archivesspace/data/indexer_state/*"
        ], check=True)
        subprocess.run([
            "docker", "exec", "archivesspace", 
            "rm", "-f", "/archivesspace/data/indexer_pui_state/*"
        ], check=True)
    finally:
        os.chdir(original_dir)


def cleanup_temp_files(tmp_dir, db_name, datestamp, local_backup_path):
    """Clean up temporary files and store the backup locally."""
    script_dir = Path(__file__).parent.absolute()
    backups_dir = script_dir / "backups"
    backups_dir.mkdir(exist_ok=True)
    
    local_filepath = backups_dir / f"{db_name}-{datestamp}.sql.gz"
    
    # Copy compressed backup to local storage if it came from temp
    if local_backup_path and not local_filepath.exists():
        local_filepath.write_bytes(local_backup_path.read_bytes())
        print(f"Stored backup locally: {local_filepath}")
    
    # Clean up temp files
    temp_files = [
        Path(tmp_dir) / f"{db_name}-{datestamp}.sql.gz",
        Path(tmp_dir) / f"{db_name}-{datestamp}.sql"
    ]
    
    for temp_file in temp_files:
        if temp_file.exists():
            temp_file.unlink()
            print(f"Cleaned up: {temp_file}")


def main():
    """Main function to orchestrate the restore process."""
    parser = argparse.ArgumentParser(description="Restore ArchivesSpace database")
    parser.add_argument("date", nargs="?", help="Date in ISO format (YYYY-MM-DD)")
    parser.add_argument("--upgrade", action="store_true", 
                       help="Run in upgrade mode (skip database restore)")
    args = parser.parse_args()
    
    if args.date == "-h":
        parser.print_help()
        sys.exit(0)
    
    # Load environment variables
    env_vars = load_env_file()
    bucket = env_vars.get('BUCKET')
    db_name = env_vars.get('DB')
    
    if not all([bucket, db_name]):
        print("Error: BUCKET and DB must be set in .env file")
        sys.exit(1)
    
    # Get datestamp
    datestamp = get_datestamp(args.date)
    print(f"Using datestamp: {datestamp}")
    
    # Use system temp directory
    tmp_dir = os.environ.get('TMPDIR', '/tmp')
    
    try:
        # Download backup from S3
        backup_path, sql_path = download_backup_from_s3(bucket, db_name, datestamp, tmp_dir)
        
        # Restore database (unless in upgrade mode)
        restore_database(db_name, datestamp, tmp_dir, args.upgrade)
        
        # Reset admin password
        reset_admin_password()
        
        # Reindex data
        reindex_data()
        
        # Clean up temporary files
        cleanup_temp_files(tmp_dir, db_name, datestamp, backup_path if sql_path else None)
        
        print("✅ Restore complete!")
        
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
