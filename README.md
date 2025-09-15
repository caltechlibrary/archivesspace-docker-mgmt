# 🦫 archivesspace-docker-mgmt

`upgrade` is a script to upgrade an existing ArchivesSpace installation to the latest version. During the process, it will:

- upgrade the codebase of the ArchivesSpace application
- restore the latest backup of the production database and soft reindex Solr

With the `--rebuild-solr` option, it will also recreate the Solr core index from scratch. Use this when there are Solr configuration or schema changes in the release.

`restore` is a script that can be run independently of `upgrade` to restore the latest backup of the production database and soft reindex Solr. It is useful for restoring a database backup without upgrading the codebase.

With an argument in the format of `YYYY-MM-DD`, it will restore the database backup from that date. If no argument is provided, it will restore the latest backup.

## .env

Be sure to create a `.env` file with at least the keys and values existing in the provided `example.env` file.
