DROP USER IF EXISTS 'ace-user'@'%';
FLUSH PRIVILEGES;
CREATE USER 'ace-user'@'%' IDENTIFIED BY 'ACE_DB_USER_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE ON `ace`.* TO 'ace-user'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON `amc`.* TO 'ace-user'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON `brocess`.* TO 'ace-user'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON `email-archive`.* TO 'ace-user'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON `vt-hash-cache`.* TO 'ace-user'@'%';
FLUSH PRIVILEGES;
