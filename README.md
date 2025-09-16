# 🦫 archivesspace-docker-mgmt

`install` is a script to install a new or upgrade an existing ArchivesSpace instance to a specified version. It will also restore the latest backup of the production database and soft reindex Solr.

Running `install --rebuild-solr` will also recreate the Solr core index from scratch. Use this when there are Solr configuration or schema changes in the release.

`db` is a script that can be run independently of `install` to restore the latest backup of the production database and soft reindex Solr in an existing ArchivesSpace instance. It is useful for restoring a database backup without upgrading the codebase.

With an argument in the format of `YYYY-MM-DD`, it will restore the database backup from that date. If no argument is provided, it will restore the latest backup.

`remove` is a script that will stop and remove the Docker containers and volumes used by ArchivesSpace. Optionally it will remove all `archivesspace-docker-v4.*` codebase directories.

## .env

Be sure to create a `.env` file with at least the keys and values existing in the provided `example.env` file.
