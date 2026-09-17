-- Demo accounts always start with explicitly supplied passwords, never a shared default.
UPDATE sys_user SET pwd_update_date=create_time WHERE pwd_update_date IS NULL;
