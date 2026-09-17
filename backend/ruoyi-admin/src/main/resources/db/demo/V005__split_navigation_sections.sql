-- Separate business navigation while retaining existing scene URLs and permissions.
UPDATE sys_menu SET menu_name='场景管理', icon='tree' WHERE menu_id=2000;
UPDATE sys_menu SET menu_name='场景列表', order_num=0 WHERE menu_id=2010;
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon)
VALUES (2020,'账号管理',0,2,'account',NULL,'M','0','0','','user');
UPDATE sys_menu SET parent_id=2020, menu_name='账号列表', order_num=0 WHERE menu_id=2001;
UPDATE sys_menu SET parent_id=2020, order_num=1 WHERE menu_id=2002;
UPDATE sys_menu SET parent_id=2020, order_num=2 WHERE menu_id=2003;
INSERT INTO sys_role_menu(role_id,menu_id) VALUES (100,2020);
