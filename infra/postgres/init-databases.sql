-- Logical databases for orchestration and experiment tracking.
-- Runs once on first postgres volume initialization.
CREATE DATABASE prefect OWNER openpali;
CREATE DATABASE mlflow OWNER openpali;
