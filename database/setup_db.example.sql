-- PakkaTrip: create the app database and its own login (run once, as the postgres superuser)
-- Copy to setup_db.sql (git-ignored), set the password to match DB_PASSWORD in backend/.env, then run:
--   "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -f database\setup_db.sql
-- CREATEDB lets Django create a throwaway database when running tests.
CREATE ROLE pakkatrip WITH LOGIN CREATEDB PASSWORD 'change-me';
CREATE DATABASE pakkatrip OWNER pakkatrip ENCODING 'UTF8';
