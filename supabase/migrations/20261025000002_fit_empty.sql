-- Zwift writes a near-empty file when a ride is started and quit; remember it as handled.
alter table fit_files drop constraint fit_files_parse_status_check;
alter table fit_files add constraint fit_files_parse_status_check check (parse_status in ('ok', 'error', 'empty'));
