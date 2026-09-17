package com.ruoyi.web;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.DemoAccountService;

@Component
public class DemoBootstrap implements ApplicationRunner {
    private final JdbcTemplate jdbc;
    public DemoBootstrap(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    @Override @Transactional
    public void run(ApplicationArguments args) {
        jdbc.queryForObject("select role_id from sys_role where role_id=100 for update", Long.class);
        if (jdbc.queryForObject("select count(*) from sys_user",Long.class)>0) return;
        String password=System.getenv("AR_BOOTSTRAP_PASSWORD");
        DemoAccountService.validatePassword(password);
        Long id=jdbc.queryForObject("insert into sys_user(dept_id,user_name,nick_name,password,status,create_time,pwd_update_date) values(100,'bootstrap','初始化管理员',?,'0',now(),now()) returning user_id",Long.class,SecurityUtils.encryptPassword(password));
        jdbc.update("insert into sys_user_role(user_id,role_id) values(?,100)",id);
    }
}
