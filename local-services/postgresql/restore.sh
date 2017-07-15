#!/usr/bin/env sh

DB_RELEASE=07-14-17

echo "Downloading latest release"
wget https://github.com/elsehow/moneybot/releases/download/$DB_RELEASE/$DB_RELEASE.sql

echo "Restoring Database to dockerized"
cat ./$DB_RELEASE.sql |  docker exec -i postgres psql -U postgres

echo "cleaning up artifacts"
rm -r ./$DB_RELEASE.sql
